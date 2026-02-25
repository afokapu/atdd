"""
Session management for ATDD sessions.

Creates GitHub Issues with Project v2 custom fields and WMBT sub-issues.
Legacy: also supports local session files in atdd-sessions/.

Usage:
    atdd new my-feature                            # Create GitHub issue + WMBT sub-issues
    atdd new my-feature --type migration            # Specify session type
    atdd session list                              # List all sessions
    atdd session archive 01                        # Archive SESSION-01-*.md

Convention: src/atdd/coach/conventions/session.convention.yaml
"""
import json
import logging
import re
import shutil
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Any

import yaml

logger = logging.getLogger(__name__)

# Step code to step name mapping
STEP_CODES = {
    "D": "Define",
    "L": "Locate",
    "P": "Prepare",
    "C": "Confirm",
    "E": "Execute",
    "M": "Monitor",
    "Y": "Modify",
    "R": "Resolve",
    "K": "Conclude",
}


class SessionManager:
    """Manage session files and GitHub Issues."""

    VALID_TYPES = {
        "implementation",
        "migration",
        "refactor",
        "analysis",
        "planning",
        "cleanup",
        "tracking",
    }

    def __init__(self, target_dir: Optional[Path] = None):
        """
        Initialize the SessionManager.

        Args:
            target_dir: Target directory containing atdd-sessions/. Defaults to cwd.
        """
        self.target_dir = target_dir or Path.cwd()
        self.sessions_dir = self.target_dir / "atdd-sessions"
        self.archive_dir = self.sessions_dir / "archive"
        self.atdd_config_dir = self.target_dir / ".atdd"
        self.manifest_file = self.atdd_config_dir / "manifest.yaml"
        self.config_file = self.atdd_config_dir / "config.yaml"

        # Package template location
        self.package_root = Path(__file__).parent.parent  # src/atdd/coach
        self.template_source = self.package_root / "templates" / "SESSION-TEMPLATE.md"
        self.wmbt_template_source = self.package_root / "templates" / "WMBT-SUBISSUE-TEMPLATE.md"

    def _check_initialized(self) -> bool:
        """Check if ATDD is initialized."""
        if not self.sessions_dir.exists():
            print(f"Error: ATDD not initialized. Run 'atdd init' first.")
            print(f"Expected: {self.sessions_dir}")
            return False
        if not self.manifest_file.exists():
            print(f"Error: Manifest not found. Run 'atdd init' first.")
            print(f"Expected: {self.manifest_file}")
            return False
        return True

    def _load_manifest(self) -> Dict[str, Any]:
        """Load the manifest.yaml file."""
        with open(self.manifest_file) as f:
            return yaml.safe_load(f) or {}

    def _save_manifest(self, manifest: Dict[str, Any]) -> None:
        """Save the manifest.yaml file."""
        with open(self.manifest_file, "w") as f:
            yaml.dump(manifest, f, default_flow_style=False, sort_keys=False)

    def _get_next_session_number(self, manifest: Dict[str, Any]) -> str:
        """Get the next available session number."""
        sessions = manifest.get("sessions", [])
        if not sessions:
            return "01"

        # Find the highest session number
        max_num = 0
        for session in sessions:
            session_id = session.get("id", "00")
            try:
                num = int(session_id)
                if num > max_num:
                    max_num = num
            except ValueError:
                continue

        # Also check for session files not in manifest
        for f in self.sessions_dir.glob("SESSION-*.md"):
            match = re.match(r"SESSION-(\d+)-", f.name)
            if match:
                try:
                    num = int(match.group(1))
                    if num > max_num:
                        max_num = num
                except ValueError:
                    continue

        return f"{max_num + 1:02d}"

    def _slugify(self, text: str) -> str:
        """Convert text to kebab-case slug."""
        # Convert to lowercase
        slug = text.lower()
        # Replace spaces and underscores with hyphens
        slug = re.sub(r"[\s_]+", "-", slug)
        # Remove non-alphanumeric characters except hyphens
        slug = re.sub(r"[^a-z0-9-]", "", slug)
        # Remove consecutive hyphens
        slug = re.sub(r"-+", "-", slug)
        # Remove leading/trailing hyphens
        slug = slug.strip("-")
        return slug

    def _load_config(self) -> Dict[str, Any]:
        """Load .atdd/config.yaml."""
        if not self.config_file.exists():
            return {}
        with open(self.config_file) as f:
            return yaml.safe_load(f) or {}

    def _has_github_config(self) -> bool:
        """Check if GitHub integration is configured."""
        config = self._load_config()
        github = config.get("github", {})
        return bool(github.get("repo") and github.get("project_id"))

    def _get_github_client(self):
        """Get a GitHubClient from config. Returns None if not configured."""
        from atdd.coach.github import GitHubClient, ProjectConfig, GitHubClientError
        try:
            project_config = ProjectConfig.from_config(self.config_file)
            return GitHubClient(
                repo=project_config.repo,
                project_id=project_config.project_id,
            )
        except GitHubClientError as e:
            logger.debug("GitHub client not available: %s", e)
            return None

    def _render_wmbt_body(
        self, wagon: str, wmbt_id: str, statement: str,
        acceptances: List[str], test_file: str,
    ) -> str:
        """Render WMBT sub-issue body from template."""
        if not self.wmbt_template_source.exists():
            # Inline fallback
            template = (
                "## wmbt:{wagon}:{wmbt_id}\n\n"
                "**Step:** {step_name} | **URN:** `wmbt:{wagon}:{wmbt_id}`\n"
                "**Statement:** {statement}\n\n"
                "### ATDD Cycle\n\n"
                "- [ ] RED: failing test written\n"
                "- [ ] GREEN: implementation passes test\n"
                "- [ ] REFACTOR: architecture compliance verified\n\n"
                "### Acceptance Criteria\n\n"
                "{acceptance_criteria}\n\n"
                "### Test File\n\n"
                "`{test_file_path}`\n"
            )
        else:
            template = self.wmbt_template_source.read_text()

        step_code = wmbt_id[0] if wmbt_id else "E"
        step_name = STEP_CODES.get(step_code, "Execute")

        if acceptances:
            acceptance_criteria = "\n".join(f"- {a}" for a in acceptances)
        else:
            acceptance_criteria = "- (no acceptance criteria defined in plan YAML)"

        return template.format(
            wagon=wagon,
            wmbt_id=wmbt_id,
            step_name=step_name,
            statement=statement,
            acceptance_criteria=acceptance_criteria,
            test_file_path=test_file,
        )

    def _discover_wmbts(self, wagon: str) -> List[Dict[str, Any]]:
        """Discover WMBTs from plan YAML for a wagon."""
        plan_dir = self.target_dir / "plan"
        wagon_snake = wagon.replace("-", "_")
        wagon_dir = plan_dir / wagon_snake

        wmbts = []
        if not wagon_dir.exists():
            logger.debug("No plan dir for wagon %s at %s", wagon, wagon_dir)
            return wmbts

        # Look for feature YAMLs containing wmbt sections
        for feature_file in sorted(wagon_dir.glob("features/*.yaml")):
            with open(feature_file) as f:
                feature_data = yaml.safe_load(f) or {}

            for wmbt in feature_data.get("wmbts", []):
                wmbt_id = wmbt.get("id", "")
                wmbts.append({
                    "id": wmbt_id,
                    "statement": wmbt.get("statement", wmbt.get("description", "")),
                    "acceptances": [
                        a.get("text", a) if isinstance(a, dict) else str(a)
                        for a in wmbt.get("acceptances", wmbt.get("acceptance_criteria", []))
                    ],
                })

        return wmbts

    def new(self, slug: str, session_type: str = "implementation", train: Optional[str] = None) -> int:
        """
        Create new session.

        If GitHub integration is configured (.atdd/config.yaml has github section),
        creates a parent GitHub Issue + WMBT sub-issues with Project v2 fields.
        Otherwise, falls back to creating a local session file.

        Args:
            slug: Session slug (will be converted to kebab-case).
            session_type: Type of session (implementation, migration, etc.).
            train: Optional train ID to assign to the session.

        Returns:
            0 on success, 1 on error.
        """
        if not self._check_initialized():
            return 1

        # Validate session type
        if session_type not in self.VALID_TYPES:
            print(f"Error: Invalid session type '{session_type}'")
            print(f"Valid types: {', '.join(sorted(self.VALID_TYPES))}")
            return 1

        # Slugify the name
        slug = self._slugify(slug)
        if not slug:
            print("Error: Invalid slug - results in empty string")
            return 1

        # Route to GitHub or local
        if self._has_github_config():
            return self._new_github_issue(slug, session_type, train=train)
        else:
            return self._new_local_file(slug, session_type)

    def _new_github_issue(self, slug: str, session_type: str, train: Optional[str] = None) -> int:
        """Create a GitHub Issue with WMBT sub-issues."""
        from atdd.coach.github import GitHubClient, ProjectConfig, GitHubClientError

        try:
            config = self._load_config()
            github_config = config["github"]
            client = GitHubClient(
                repo=github_config["repo"],
                project_id=github_config.get("project_id"),
            )
        except (GitHubClientError, KeyError) as e:
            print(f"Error: GitHub integration failed: {e}")
            return 1

        today = date.today().isoformat()
        title_text = slug.replace("-", " ").title()
        title = f"feat(atdd): {title_text}"

        # Build parent issue body (minimal — details added by user)
        train_display = train or "TBD"
        body = (
            f"## Session Metadata\n\n"
            f"| Field | Value |\n"
            f"|-------|-------|\n"
            f"| Date | `{today}` |\n"
            f"| Status | `INIT` |\n"
            f"| Type | `{session_type}` |\n"
            f"| Branch | TBD |\n"
            f"| Archetypes | TBD |\n"
            f"| Train | {train_display} |\n"
            f"| Feature | TBD |\n\n"
            f"---\n\n"
            f"## Context\n\n"
            f"(fill in)\n\n"
            f"---\n\n"
            f"## Session Log\n\n"
            f"### Session 1 ({today})\n\n"
            f"**Completed:**\n"
            f"- Session created via `atdd new {slug}`\n"
        )

        # Determine labels for parent
        parent_labels = ["atdd-session", f"atdd:INIT"]

        # Create parent issue
        print(f"Creating parent issue...")
        parent_number = client.create_issue(
            title=title,
            body=body,
            labels=parent_labels,
        )
        print(f"  Created #{parent_number}: {title}")

        # Add to Project v2 and set fields
        try:
            item_id = client.add_issue_to_project(parent_number)
            fields = client.get_project_fields()

            # Set Session Number
            if "Session Number" in fields:
                client.set_project_field_number(
                    item_id, fields["Session Number"]["id"], parent_number
                )

            # Set ATDD Status = INIT
            if "ATDD Status" in fields:
                options = fields["ATDD Status"].get("options", {})
                if "INIT" in options:
                    client.set_project_field_select(
                        item_id, fields["ATDD Status"]["id"], options["INIT"]
                    )

            # Set Session Type
            if "Session Type" in fields:
                options = fields["Session Type"].get("options", {})
                if session_type in options:
                    client.set_project_field_select(
                        item_id, fields["Session Type"]["id"], options[session_type]
                    )

            # Set ATDD Phase = Planner
            if "ATDD Phase" in fields:
                options = fields["ATDD Phase"].get("options", {})
                if "Planner" in options:
                    client.set_project_field_select(
                        item_id, fields["ATDD Phase"]["id"], options["Planner"]
                    )

            # E008: Set Train field if provided
            if train and "Train" in fields:
                client.set_project_field_text(
                    item_id, fields["Train"]["id"], train
                )

            print(f"  Added to Project with custom fields")
        except GitHubClientError as e:
            print(f"  Warning: Could not add to Project: {e}")

        # Discover WMBTs from plan YAML
        wagon = slug  # Default: wagon slug = session slug
        wmbts = self._discover_wmbts(wagon)

        wmbt_count = 0
        if wmbts:
            print(f"Creating {len(wmbts)} WMBT sub-issues...")
            for wmbt in wmbts:
                wmbt_id = wmbt["id"]
                statement = wmbt["statement"]
                acceptances = wmbt["acceptances"]
                step_code = wmbt_id[0] if wmbt_id else "E"
                step_name = STEP_CODES.get(step_code, "Execute")

                sub_title = f"wmbt:{wagon}:{wmbt_id} — {statement}"
                sub_body = self._render_wmbt_body(
                    wagon=wagon,
                    wmbt_id=wmbt_id,
                    statement=statement,
                    acceptances=acceptances,
                    test_file=f"src/atdd/coach/commands/tests/test_{wmbt_id}_{slug}.py",
                )

                sub_number = client.create_issue(
                    title=sub_title,
                    body=sub_body,
                    labels=["atdd-wmbt"],
                )
                print(f"  Created #{sub_number}: wmbt:{wagon}:{wmbt_id}")

                # Link as sub-issue
                try:
                    client.add_sub_issue(parent_number, sub_number)
                except GitHubClientError as e:
                    print(f"    Warning: Could not link sub-issue: {e}")

                # Add to Project and set WMBT fields
                try:
                    sub_item_id = client.add_issue_to_project(sub_number)
                    if "WMBT ID" in fields:
                        client.set_project_field_text(
                            sub_item_id, fields["WMBT ID"]["id"], wmbt_id
                        )
                    if "WMBT Step" in fields:
                        step_options = fields["WMBT Step"].get("options", {})
                        if step_name in step_options:
                            client.set_project_field_select(
                                sub_item_id, fields["WMBT Step"]["id"],
                                step_options[step_name],
                            )
                except GitHubClientError as e:
                    print(f"    Warning: Could not set Project fields: {e}")

                wmbt_count += 1

        # Update manifest
        manifest = self._load_manifest()
        session_entry = {
            "id": f"{parent_number:02d}" if parent_number < 100 else str(parent_number),
            "slug": slug,
            "file": None,
            "issue_number": parent_number,
            "type": session_type,
            "status": "INIT",
            "created": today,
            "archived": None,
        }
        if "sessions" not in manifest:
            manifest["sessions"] = []
        manifest["sessions"].append(session_entry)
        self._save_manifest(manifest)

        print(f"\nCreated #{parent_number} with {wmbt_count} WMBTs")
        print(f"  Repo: {github_config['repo']}")
        print(f"  Type: {session_type}")
        print(f"  Status: INIT")

        return 0

    def _new_local_file(self, slug: str, session_type: str) -> int:
        """Create a local session file (legacy path)."""
        # Load manifest
        manifest = self._load_manifest()

        # Get next session number
        session_num = self._get_next_session_number(manifest)

        # Generate filename
        filename = f"SESSION-{session_num}-{slug}.md"
        session_path = self.sessions_dir / filename

        if session_path.exists():
            print(f"Error: Session already exists: {session_path}")
            return 1

        # Read template
        if not self.template_source.exists():
            print(f"Error: Template not found: {self.template_source}")
            return 1

        template_content = self.template_source.read_text()

        # Replace placeholders in template
        today = date.today().isoformat()
        title = slug.replace("-", " ").title()

        # Replace frontmatter placeholders
        content = template_content
        content = re.sub(r'session:\s*"\{NN\}"', f'session: "{session_num}"', content)
        content = re.sub(r'title:\s*"\{Title\}"', f'title: "{title}"', content)
        content = re.sub(r'date:\s*"\{YYYY-MM-DD\}"', f'date: "{today}"', content)
        content = re.sub(r'type:\s*"\{type\}"', f'type: "{session_type}"', content)

        # Replace markdown header
        content = re.sub(
            r"# SESSION-\{NN\}: \{Title\}",
            f"# SESSION-{session_num}: {title}",
            content,
        )

        # Write session file
        session_path.write_text(content)
        print(f"Created: {session_path}")

        # Update manifest
        session_entry = {
            "id": session_num,
            "slug": slug,
            "file": filename,
            "type": session_type,
            "status": "INIT",
            "created": today,
            "archived": None,
        }

        if "sessions" not in manifest:
            manifest["sessions"] = []
        manifest["sessions"].append(session_entry)

        self._save_manifest(manifest)
        print(f"Updated: {self.manifest_file}")

        print(f"\nSession created: {filename}")
        print(f"  Type: {session_type}")
        print(f"  Status: INIT")
        print(f"\nNext: Edit {session_path} and update status to PLANNED")

        return 0

    # -------------------------------------------------------------------------
    # E002: list
    # -------------------------------------------------------------------------

    def list(self) -> int:
        """List sessions. Uses GitHub API if configured, else manifest."""
        if not self._check_initialized():
            return 1

        if self._has_github_config():
            return self._list_github()
        return self._list_local()

    def _list_github(self) -> int:
        """List sessions from GitHub Issues with sub-issue progress."""
        from atdd.coach.github import GitHubClientError

        try:
            client = self._get_github_client()
            issues = client.list_issues_by_label("atdd-session")
        except (GitHubClientError, Exception) as e:
            print(f"Error: {e}")
            return 1

        if not issues:
            print("No sessions found.")
            print("Create one with: atdd new my-feature")
            return 0

        print("\n" + "=" * 80)
        print("ATDD Sessions")
        print("=" * 80)
        print(f"{'#':<6} {'Status':<12} {'Progress':<10} {'Title':<50}")
        print("-" * 80)

        for issue in sorted(issues, key=lambda x: x["number"]):
            num = issue["number"]
            title = issue["title"][:50]
            labels = [l["name"] for l in issue.get("labels", [])]

            # Extract status from atdd:* label
            status = "UNKNOWN"
            for label in labels:
                if label.startswith("atdd:") and label != "atdd-session":
                    status = label.split(":")[1]
                    break

            # Get sub-issue progress
            try:
                subs = client.get_sub_issues(num)
                total = len(subs)
                closed = sum(1 for s in subs if s.get("state") == "closed")
                progress = f"{closed}/{total}" if total > 0 else "-"
            except Exception:
                progress = "?"

            print(f"#{num:<5} {status:<12} {progress:<10} {title}")

        print("-" * 80)
        print(f"Total: {len(issues)} sessions")
        return 0

    def _list_local(self) -> int:
        """List sessions from manifest (legacy)."""
        manifest = self._load_manifest()
        sessions = manifest.get("sessions", [])

        if not sessions:
            print("No sessions found.")
            print("Create one with: atdd new my-feature")
            return 0

        print("\n" + "=" * 70)
        print("ATDD Sessions")
        print("=" * 70)
        print(f"{'ID':<4} {'Status':<10} {'Type':<15} {'File':<40}")
        print("-" * 70)

        active = [s for s in sessions if not s.get("archived")]
        archived = [s for s in sessions if s.get("archived")]

        for session in active:
            sid = session.get("id", "??")
            status = session.get("status", "UNKNOWN")
            stype = session.get("type", "unknown")
            fname = session.get("file") or f"#{session.get('issue_number', '?')}"
            print(f"{sid:<4} {status:<10} {stype:<15} {fname:<40}")

        if archived:
            print("\n--- Archived ---")
            for session in archived:
                sid = session.get("id", "??")
                status = session.get("status", "UNKNOWN")
                stype = session.get("type", "unknown")
                fname = session.get("file") or f"#{session.get('issue_number', '?')}"
                print(f"{sid:<4} {status:<10} {stype:<15} {fname:<40}")

        print("-" * 70)
        print(f"Total: {len(sessions)} sessions ({len(active)} active, {len(archived)} archived)")
        return 0

    # -------------------------------------------------------------------------
    # E003: archive
    # -------------------------------------------------------------------------

    def archive(self, session_id: str) -> int:
        """Archive a session. Closes GitHub issue + sub-issues if configured."""
        if not self._check_initialized():
            return 1

        if self._has_github_config():
            return self._archive_github(session_id)
        return self._archive_local(session_id)

    def _archive_github(self, session_id: str) -> int:
        """Close parent issue + all sub-issues on GitHub."""
        from atdd.coach.github import GitHubClientError

        try:
            issue_number = int(session_id)
        except ValueError:
            print(f"Error: Invalid issue number '{session_id}'")
            return 1

        try:
            client = self._get_github_client()
            issue = client.get_issue(issue_number)
        except (GitHubClientError, Exception) as e:
            print(f"Error: {e}")
            return 1

        if issue.get("state") == "closed":
            print(f"#{issue_number} is already closed.")
            return 0

        # Close all open sub-issues
        try:
            subs = client.get_sub_issues(issue_number)
            closed_count = 0
            for sub in subs:
                if sub.get("state") == "open":
                    client.close_issue(sub["number"])
                    print(f"  Closed sub-issue #{sub['number']}")
                    closed_count += 1
        except GitHubClientError as e:
            print(f"  Warning: Could not close sub-issues: {e}")
            closed_count = 0

        # Close parent
        client.close_issue(issue_number)
        print(f"  Closed parent #{issue_number}")

        # Swap label to atdd:COMPLETE
        try:
            # Remove existing phase labels
            labels = [l["name"] for l in issue.get("labels", [])]
            phase_labels = [l for l in labels if l.startswith("atdd:") and l != "atdd-session"]
            if phase_labels:
                client.remove_label(issue_number, phase_labels)
            client.add_label(issue_number, ["atdd:COMPLETE"])
        except GitHubClientError as e:
            print(f"  Warning: Could not update labels: {e}")

        # Update Project field
        try:
            fields = client.get_project_fields()
            item_id = client.get_project_item_id(issue_number)
            if item_id and "ATDD Status" in fields:
                options = fields["ATDD Status"].get("options", {})
                if "COMPLETE" in options:
                    client.set_project_field_select(
                        item_id, fields["ATDD Status"]["id"], options["COMPLETE"]
                    )
        except GitHubClientError:
            pass

        # Update manifest
        manifest = self._load_manifest()
        for s in manifest.get("sessions", []):
            if s.get("issue_number") == issue_number:
                s["status"] = "COMPLETE"
                s["archived"] = date.today().isoformat()
                break
        self._save_manifest(manifest)

        total_subs = len(subs) if subs else 0
        print(f"\nArchived #{issue_number}: closed {closed_count} sub-issues, "
              f"{total_subs} total")
        return 0

    def _archive_local(self, session_id: str) -> int:
        """Move local session file to archive/ (legacy)."""
        try:
            session_num = int(session_id)
            session_id_normalized = f"{session_num:02d}"
        except ValueError:
            print(f"Error: Invalid session ID '{session_id}'")
            return 1

        manifest = self._load_manifest()
        sessions = manifest.get("sessions", [])

        session_entry = None
        session_index = None
        for i, s in enumerate(sessions):
            if s.get("id") == session_id_normalized:
                session_entry = s
                session_index = i
                break

        if session_entry is None:
            print(f"Error: Session {session_id_normalized} not found in manifest")
            return 1

        if session_entry.get("archived"):
            print(f"Error: Session {session_id_normalized} is already archived")
            return 1

        filename = session_entry.get("file")
        if not filename:
            print(f"Error: No file for session {session_id_normalized} (GitHub issue?)")
            return 1

        session_path = self.sessions_dir / filename
        if not session_path.exists():
            pattern = f"SESSION-{session_id_normalized}-*.md"
            matches = list(self.sessions_dir.glob(pattern))
            if matches:
                session_path = matches[0]
                filename = session_path.name
            else:
                print(f"Error: Session file not found: {filename}")
                return 1

        self.archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = self.archive_dir / filename
        shutil.move(str(session_path), str(archive_path))
        print(f"Moved: {session_path} -> {archive_path}")

        session_entry["archived"] = date.today().isoformat()
        session_entry["file"] = f"archive/{filename}"
        manifest["sessions"][session_index] = session_entry
        self._save_manifest(manifest)
        print(f"Updated: {self.manifest_file}")
        print(f"\nSession {session_id_normalized} archived successfully")
        return 0

    # -------------------------------------------------------------------------
    # E004: update
    # -------------------------------------------------------------------------

    VALID_TRANSITIONS = {
        "INIT": {"PLANNED", "BLOCKED", "OBSOLETE"},
        "PLANNED": {"RED", "BLOCKED", "OBSOLETE"},
        "RED": {"GREEN", "BLOCKED", "OBSOLETE"},
        "GREEN": {"REFACTOR", "BLOCKED", "OBSOLETE"},
        "REFACTOR": {"COMPLETE", "BLOCKED", "OBSOLETE"},
        "BLOCKED": {"INIT", "PLANNED", "RED", "GREEN", "REFACTOR", "OBSOLETE"},
        "COMPLETE": set(),
        "OBSOLETE": set(),
    }

    def update(
        self,
        session_id: str,
        status: Optional[str] = None,
        phase: Optional[str] = None,
        branch: Optional[str] = None,
        train: Optional[str] = None,
        feature_urn: Optional[str] = None,
        archetypes: Optional[str] = None,
        complexity: Optional[str] = None,
    ) -> int:
        """Update session Project fields and labels."""
        if not self._has_github_config():
            print("Error: GitHub integration not configured. Run 'atdd init' first.")
            return 1

        from atdd.coach.github import GitHubClientError

        try:
            issue_number = int(session_id)
        except ValueError:
            print(f"Error: Invalid issue number '{session_id}'")
            return 1

        try:
            client = self._get_github_client()
            issue = client.get_issue(issue_number)
            fields = client.get_project_fields()
            item_id = client.get_project_item_id(issue_number)
        except (GitHubClientError, Exception) as e:
            print(f"Error: {e}")
            return 1

        if not item_id:
            print(f"Error: #{issue_number} not found in Project")
            return 1

        updated = []

        # Status transition with validation
        if status:
            status = status.upper()
            current_labels = [l["name"] for l in issue.get("labels", [])]
            current_status = "UNKNOWN"
            for label in current_labels:
                if label.startswith("atdd:") and label != "atdd-session":
                    current_status = label.split(":")[1]
                    break

            allowed = self.VALID_TRANSITIONS.get(current_status, set())
            if status not in allowed and current_status != "UNKNOWN":
                print(f"Error: Cannot transition from {current_status} to {status}")
                print(f"  Allowed: {', '.join(sorted(allowed)) or '(terminal state)'}")
                return 1

            # E008: Enforce train assignment for transitions past PLANNED
            post_planned = {"RED", "GREEN", "REFACTOR", "COMPLETE"}
            if status in post_planned and not train:
                # Check if Train is already set on the project item
                try:
                    field_values = client.get_project_item_field_values(item_id)
                    current_train = (field_values.get("Train") or "").strip()
                    if not current_train or current_train.upper() == "TBD":
                        print(f"Error: Train field required before transitioning to {status}")
                        print(f"  Current Train: {current_train or '(empty)'}")
                        print(f"  Fix: atdd update {session_id} --status {status} --train <train_id>")
                        return 1
                except GitHubClientError:
                    # If we can't read fields, allow the transition (fail open)
                    logger.debug("Could not read Train field, allowing transition")

            # Swap phase label
            phase_labels = [l for l in current_labels if l.startswith("atdd:") and l != "atdd-session"]
            if phase_labels:
                client.remove_label(issue_number, phase_labels)
            client.add_label(issue_number, [f"atdd:{status}"])

            # Update Project field
            if "ATDD Status" in fields:
                options = fields["ATDD Status"].get("options", {})
                if status in options:
                    client.set_project_field_select(
                        item_id, fields["ATDD Status"]["id"], options[status]
                    )
            updated.append(f"status: {status}")

        # Phase (Planner/Tester/Coder)
        if phase:
            phase_cap = phase.capitalize()
            if "ATDD Phase" in fields:
                options = fields["ATDD Phase"].get("options", {})
                if phase_cap in options:
                    client.set_project_field_select(
                        item_id, fields["ATDD Phase"]["id"], options[phase_cap]
                    )
                    updated.append(f"phase: {phase_cap}")
                else:
                    print(f"Warning: Unknown phase '{phase_cap}'")

        # Text fields
        text_updates = {
            "Branch": branch,
            "Train": train,
            "Feature URN": feature_urn,
            "Archetypes": archetypes,
        }
        for field_name, value in text_updates.items():
            if value and field_name in fields:
                client.set_project_field_text(item_id, fields[field_name]["id"], value)
                updated.append(f"{field_name.lower()}: {value}")

        # Complexity
        if complexity:
            if "Complexity" in fields:
                options = fields["Complexity"].get("options", {})
                if complexity in options:
                    client.set_project_field_select(
                        item_id, fields["Complexity"]["id"], options[complexity]
                    )
                    updated.append(f"complexity: {complexity}")

        if updated:
            print(f"Updated #{issue_number}:")
            for u in updated:
                print(f"  {u}")
        else:
            print("Nothing to update.")

        return 0

    # -------------------------------------------------------------------------
    # E005: close-wmbt
    # -------------------------------------------------------------------------

    def close_wmbt(self, session_id: str, wmbt_id: str, force: bool = False) -> int:
        """Close a WMBT sub-issue by ID."""
        if not self._has_github_config():
            print("Error: GitHub integration not configured.")
            return 1

        from atdd.coach.github import GitHubClientError

        try:
            issue_number = int(session_id)
        except ValueError:
            print(f"Error: Invalid issue number '{session_id}'")
            return 1

        try:
            client = self._get_github_client()
            subs = client.get_sub_issues(issue_number)
        except (GitHubClientError, Exception) as e:
            print(f"Error: {e}")
            return 1

        # Find sub-issue matching WMBT ID
        wmbt_id_upper = wmbt_id.upper()
        target = None
        for sub in subs:
            title = sub.get("title", "")
            # Match pattern: wmbt:*:{WMBT_ID}
            if f":{wmbt_id_upper}" in title.upper():
                target = sub
                break

        if not target:
            print(f"Error: No sub-issue found for WMBT {wmbt_id_upper} in #{issue_number}")
            available = [s["title"].split(":")[-1].split(" ")[0].strip() for s in subs]
            if available:
                print(f"  Available: {', '.join(available)}")
            return 1

        if target.get("state") == "closed":
            print(f"WMBT {wmbt_id_upper} (#{target['number']}) is already closed.")
            return 0

        # Check ATDD cycle checkboxes (warn if not all checked)
        body = target.get("body", "")
        unchecked = body.count("- [ ]")
        if unchecked > 0 and not force:
            print(f"Warning: {unchecked} unchecked ATDD cycle item(s) in #{target['number']}")
            print(f"  Use --force to close anyway")
            return 1

        # Close the sub-issue
        client.close_issue(target["number"])

        # Calculate progress
        total = len(subs)
        closed = sum(1 for s in subs if s.get("state") == "closed") + 1  # +1 for the one we just closed
        print(f"Closed {target['title']}")
        print(f"  Progress: {closed}/{total}")

        return 0

    def sync(self) -> int:
        """
        Sync manifest with actual session files.

        Scans atdd-sessions/ and updates manifest to match actual files.

        Returns:
            0 on success, 1 on error.
        """
        if not self._check_initialized():
            return 1

        manifest = self._load_manifest()
        existing_sessions = {s.get("file"): s for s in manifest.get("sessions", [])}

        # Scan for session files
        found_files = set()
        new_sessions = []

        # Scan main directory
        for f in self.sessions_dir.glob("SESSION-*.md"):
            if f.name == "SESSION-TEMPLATE.md":
                continue

            found_files.add(f.name)

            if f.name not in existing_sessions:
                # Parse filename to extract info
                match = re.match(r"SESSION-(\d+)-(.+)\.md", f.name)
                if match:
                    session_id = match.group(1)
                    slug = match.group(2)

                    new_sessions.append({
                        "id": session_id,
                        "slug": slug,
                        "file": f.name,
                        "type": "unknown",
                        "status": "UNKNOWN",
                        "created": date.today().isoformat(),
                        "archived": None,
                    })

        # Scan archive directory
        if self.archive_dir.exists():
            for f in self.archive_dir.glob("SESSION-*.md"):
                archive_path = f"archive/{f.name}"
                found_files.add(archive_path)

                if archive_path not in existing_sessions:
                    match = re.match(r"SESSION-(\d+)-(.+)\.md", f.name)
                    if match:
                        session_id = match.group(1)
                        slug = match.group(2)

                        new_sessions.append({
                            "id": session_id,
                            "slug": slug,
                            "file": archive_path,
                            "type": "unknown",
                            "status": "UNKNOWN",
                            "created": date.today().isoformat(),
                            "archived": date.today().isoformat(),
                        })

        # Add new sessions to manifest
        if new_sessions:
            manifest["sessions"] = manifest.get("sessions", []) + new_sessions
            print(f"Added {len(new_sessions)} new session(s) to manifest")

        # Report missing files
        for filename, session in existing_sessions.items():
            if filename not in found_files and f"archive/{filename}" not in found_files:
                print(f"Warning: Session file not found: {filename}")

        self._save_manifest(manifest)
        print(f"Manifest synced: {self.manifest_file}")

        return 0
