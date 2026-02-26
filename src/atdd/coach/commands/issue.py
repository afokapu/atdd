"""
Issue management for ATDD tracking via GitHub Issues.

Creates GitHub Issues with Project v2 custom fields and WMBT sub-issues.
Requires `gh` CLI authenticated with `project` scope.

Usage:
    atdd new my-feature                            # Create GitHub issue + WMBT sub-issues
    atdd new my-feature --type migration            # Specify issue type
    atdd list                                      # List all issues
    atdd archive 11                                # Archive issue
    atdd update 11 --status RED                    # Update issue fields
    atdd close-wmbt 11 D005                        # Close WMBT sub-issue

Convention: src/atdd/coach/conventions/issue.convention.yaml
"""
import json
import logging
import re
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

# Archetype-specific gate test rows for the Validation table.
# Each entry: (gate_id, phase, command, validator_path)
ARCHETYPE_GATES = {
    "be": [
        ("GT-010", "implementation", "atdd validate coder", "src/atdd/coder/validators/test_python_architecture.py"),
        ("GT-011", "implementation", "atdd validate coder", "src/atdd/coder/validators/test_import_boundaries.py"),
    ],
    "fe": [
        ("GT-020", "implementation", "atdd validate coder", "src/atdd/coder/validators/test_typescript_architecture.py"),
    ],
    "contracts": [
        ("GT-030", "tester", "atdd validate tester", "src/atdd/tester/validators/test_contract_schema_compliance.py"),
    ],
    "wmbt": [
        ("GT-040", "planner", "atdd validate planner", "src/atdd/planner/validators/test_wmbt_consistency.py"),
    ],
    "wagon": [
        ("GT-050", "planner", "atdd validate planner", "src/atdd/planner/validators/test_wagon_urn_chain.py"),
    ],
    "train": [
        ("GT-060", "planner", "atdd validate planner", "src/atdd/planner/validators/test_train_validation.py"),
    ],
    "db": [
        ("GT-070", "implementation", "supabase db push --dry-run", "supabase/migrations/"),
    ],
    "migrations": [
        ("GT-071", "implementation", "supabase db push --dry-run", "supabase/migrations/"),
    ],
    "telemetry": [
        ("GT-080", "tester", "atdd validate tester", "src/atdd/tester/validators/test_telemetry_validation.py"),
    ],
}


class IssueManager:
    """Manage ATDD issues via GitHub Issues and Projects v2."""

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
        Initialize the IssueManager.

        Args:
            target_dir: Target directory containing .atdd/ config. Defaults to cwd.
        """
        self.target_dir = target_dir or Path.cwd()
        self.atdd_config_dir = self.target_dir / ".atdd"
        self.manifest_file = self.atdd_config_dir / "manifest.yaml"
        self.config_file = self.atdd_config_dir / "config.yaml"

        # Package template location
        self.package_root = Path(__file__).parent.parent  # src/atdd/coach
        self.wmbt_template_source = self.package_root / "templates" / "WMBT-SUBISSUE-TEMPLATE.md"
        self.parent_template_source = self.package_root / "templates" / "PARENT-ISSUE-TEMPLATE.md"

    def _check_initialized(self) -> bool:
        """Check if ATDD is initialized with GitHub integration."""
        if not self.config_file.exists():
            print("Error: ATDD not initialized. Run 'atdd init' first.")
            print(f"Expected: {self.config_file}")
            return False
        if not self._has_github_config():
            print("Error: GitHub integration not configured. Run 'atdd init' first.")
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

    def _build_gate_test_rows(self, archetypes_list: List[str]) -> str:
        """Build archetype-specific gate test table rows."""
        rows = []
        for arch in archetypes_list:
            for gate_id, phase, command, validator in ARCHETYPE_GATES.get(arch, []):
                rows.append(
                    f"| {gate_id} | {phase} | `{command}` | PASS | `{validator}` | TODO |"
                )
        if rows:
            return "\n".join(rows) + "\n"
        return ""

    def _render_parent_body(
        self,
        slug: str,
        issue_type: str,
        today: str,
        train_display: str,
        archetypes_display: str,
    ) -> str:
        """Render parent issue body from template.

        Falls back to inline minimal body if the template file is missing.
        """
        archetypes_list = [
            a.strip() for a in archetypes_display.split(",") if a.strip() and a.strip() != "TBD"
        ]

        # Conditional Data Model section
        has_db = any(a in ("db", "migrations") for a in archetypes_list)
        if has_db:
            data_model_section = (
                "### Data Model\n\n"
                "```sql\n"
                "-- Table/view definitions\n"
                "CREATE TABLE IF NOT EXISTS public.example (\n"
                "  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n"
                "  data JSONB NOT NULL,\n"
                "  created_at TIMESTAMPTZ DEFAULT NOW(),\n"
                "  updated_at TIMESTAMPTZ DEFAULT NOW()\n"
                ");\n"
                "```"
            )
        else:
            data_model_section = ""

        gate_tests_rows = self._build_gate_test_rows(archetypes_list)

        if not self.parent_template_source.exists():
            return self._render_parent_body_inline(
                slug, issue_type, today, train_display, archetypes_display,
            )

        template = self.parent_template_source.read_text()
        return template.format(
            today=today,
            slug=slug,
            issue_type=issue_type,
            train_display=train_display,
            archetypes_display=archetypes_display,
            data_model_section=data_model_section,
            gate_tests_rows=gate_tests_rows,
        )

    def _render_parent_body_inline(
        self,
        slug: str,
        issue_type: str,
        today: str,
        train_display: str,
        archetypes_display: str,
    ) -> str:
        """Inline fallback body when template file is missing."""
        return (
            f"## Issue Metadata\n\n"
            f"| Field | Value |\n"
            f"|-------|-------|\n"
            f"| Date | `{today}` |\n"
            f"| Status | `INIT` |\n"
            f"| Type | `{issue_type}` |\n"
            f"| Branch | TBD |\n"
            f"| Archetypes | {archetypes_display} |\n"
            f"| Train | {train_display} |\n"
            f"| Feature | TBD |\n\n"
            f"---\n\n"
            f"## Context\n\n"
            f"(fill in)\n\n"
            f"---\n\n"
            f"## Activity Log\n\n"
            f"### Entry 1 ({today})\n\n"
            f"**Completed:**\n"
            f"- Issue created via `atdd new {slug}`\n"
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

    def new(
        self,
        slug: str,
        issue_type: str = "implementation",
        train: Optional[str] = None,
        archetypes: Optional[str] = None,
    ) -> int:
        """
        Create new issue.

        Creates a parent GitHub Issue + WMBT sub-issues with Project v2 fields.

        Args:
            slug: Issue slug (will be converted to kebab-case).
            issue_type: Type of issue (implementation, migration, etc.).
            train: Optional train ID to assign to the issue.
            archetypes: Optional comma-separated archetype IDs (e.g., "be,contracts,wmbt").

        Returns:
            0 on success, 1 on error.
        """
        if not self._check_initialized():
            return 1

        # Validate issue type
        if issue_type not in self.VALID_TYPES:
            print(f"Error: Invalid issue type '{issue_type}'")
            print(f"Valid types: {', '.join(sorted(self.VALID_TYPES))}")
            return 1

        # Slugify the name
        slug = self._slugify(slug)
        if not slug:
            print("Error: Invalid slug - results in empty string")
            return 1

        return self._new_github_issue(slug, issue_type, train=train, archetypes=archetypes)

    def _new_github_issue(
        self,
        slug: str,
        issue_type: str,
        train: Optional[str] = None,
        archetypes: Optional[str] = None,
    ) -> int:
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

        train_display = train or "TBD"
        archetypes_display = archetypes if archetypes else "TBD"

        # Render full-structure body from template
        body = self._render_parent_body(
            slug, issue_type, today, train_display, archetypes_display,
        )

        # Determine labels for parent
        parent_labels = ["atdd-issue", "atdd:INIT"]

        # Add archetype labels
        if archetypes:
            for arch in archetypes.split(","):
                arch = arch.strip()
                if arch:
                    parent_labels.append(f"archetype:{arch}")

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

            # Set ATDD: Status = INIT
            if "ATDD: Status" in fields:
                options = fields["ATDD: Status"].get("options", {})
                if "INIT" in options:
                    client.set_project_field_select(
                        item_id, fields["ATDD: Status"]["id"], options["INIT"]
                    )

            # Set issue type (Project field: "ATDD: Issue Type")
            if "ATDD: Issue Type" in fields:
                options = fields["ATDD: Issue Type"].get("options", {})
                if issue_type in options:
                    client.set_project_field_select(
                        item_id, fields["ATDD: Issue Type"]["id"], options[issue_type]
                    )

            # Set ATDD: Phase = Planner
            if "ATDD: Phase" in fields:
                options = fields["ATDD: Phase"].get("options", {})
                if "Planner" in options:
                    client.set_project_field_select(
                        item_id, fields["ATDD: Phase"]["id"], options["Planner"]
                    )

            # E008: Set Train field if provided
            if train and "ATDD: Train" in fields:
                client.set_project_field_text(
                    item_id, fields["ATDD: Train"]["id"], train
                )

            # E010: Set Archetypes field if provided
            if archetypes and "ATDD: Archetypes" in fields:
                client.set_project_field_text(
                    item_id, fields["ATDD: Archetypes"]["id"], archetypes
                )

            print(f"  Added to Project with custom fields")
        except GitHubClientError as e:
            print(f"  Warning: Could not add to Project: {e}")

        # Discover WMBTs from plan YAML
        wagon = slug  # Default: wagon slug = issue slug
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
                    if "ATDD: WMBT ID" in fields:
                        client.set_project_field_text(
                            sub_item_id, fields["ATDD: WMBT ID"]["id"], wmbt_id
                        )
                    if "ATDD: WMBT Step" in fields:
                        step_options = fields["ATDD: WMBT Step"].get("options", {})
                        if step_name in step_options:
                            client.set_project_field_select(
                                sub_item_id, fields["ATDD: WMBT Step"]["id"],
                                step_options[step_name],
                            )
                except GitHubClientError as e:
                    print(f"    Warning: Could not set Project fields: {e}")

                wmbt_count += 1

        # Update manifest
        manifest = self._load_manifest()
        issue_entry = {
            "id": f"{parent_number:02d}" if parent_number < 100 else str(parent_number),
            "slug": slug,
            "file": None,
            "issue_number": parent_number,
            "type": issue_type,
            "status": "INIT",
            "created": today,
            "archived": None,
        }
        if "sessions" not in manifest:
            manifest["sessions"] = []
        manifest["sessions"].append(issue_entry)
        self._save_manifest(manifest)

        print(f"\nCreated #{parent_number} with {wmbt_count} WMBTs")
        print(f"  Repo: {github_config['repo']}")
        print(f"  Type: {issue_type}")
        print(f"  Status: INIT")

        return 0

    # -------------------------------------------------------------------------
    # E002: list
    # -------------------------------------------------------------------------

    def list(self) -> int:
        """List issues from GitHub."""
        if not self._check_initialized():
            return 1

        return self._list_github()

    def _list_github(self) -> int:
        """List issues from GitHub with sub-issue progress."""
        from atdd.coach.github import GitHubClientError

        try:
            client = self._get_github_client()
            issues = client.list_issues_by_label("atdd-issue")
        except (GitHubClientError, Exception) as e:
            print(f"Error: {e}")
            return 1

        if not issues:
            print("No issues found.")
            print("Create one with: atdd new my-feature")
            return 0

        print("\n" + "=" * 80)
        print("ATDD Issues")
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
                if label.startswith("atdd:") and label != "atdd-issue":
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
        print(f"Total: {len(issues)} issues")
        return 0

    # -------------------------------------------------------------------------
    # E003: archive
    # -------------------------------------------------------------------------

    def archive(self, issue_id: str) -> int:
        """Archive an issue. Closes parent + all sub-issues on GitHub."""
        if not self._check_initialized():
            return 1

        return self._archive_github(issue_id)

    def _archive_github(self, issue_id: str) -> int:
        """Close parent issue + all sub-issues on GitHub."""
        from atdd.coach.github import GitHubClientError

        try:
            issue_number = int(issue_id)
        except ValueError:
            print(f"Error: Invalid issue number '{issue_id}'")
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
            labels = [l["name"] for l in issue.get("labels", [])]
            phase_labels = [l for l in labels if l.startswith("atdd:") and l != "atdd-issue"]
            if phase_labels:
                client.remove_label(issue_number, phase_labels)
            client.add_label(issue_number, ["atdd:COMPLETE"])
        except GitHubClientError as e:
            print(f"  Warning: Could not update labels: {e}")

        # Update Project field
        try:
            fields = client.get_project_fields()
            item_id = client.get_project_item_id(issue_number)
            if item_id and "ATDD: Status" in fields:
                options = fields["ATDD: Status"].get("options", {})
                if "COMPLETE" in options:
                    client.set_project_field_select(
                        item_id, fields["ATDD: Status"]["id"], options["COMPLETE"]
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
        issue_id: str,
        status: Optional[str] = None,
        phase: Optional[str] = None,
        branch: Optional[str] = None,
        train: Optional[str] = None,
        feature_urn: Optional[str] = None,
        archetypes: Optional[str] = None,
        complexity: Optional[str] = None,
    ) -> int:
        """Update issue Project fields and labels."""
        if not self._check_initialized():
            return 1

        from atdd.coach.github import GitHubClientError

        try:
            issue_number = int(issue_id)
        except ValueError:
            print(f"Error: Invalid issue number '{issue_id}'")
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
                if label.startswith("atdd:") and label != "atdd-issue":
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
                    current_train = (field_values.get("ATDD: Train") or "").strip()
                    if not current_train or current_train.upper() == "TBD":
                        print(f"Error: Train field required before transitioning to {status}")
                        print(f"  Current Train: {current_train or '(empty)'}")
                        print(f"  Fix: atdd update {issue_id} --status {status} --train <train_id>")
                        return 1
                except GitHubClientError:
                    # If we can't read fields, allow the transition (fail open)
                    logger.debug("Could not read Train field, allowing transition")

            # Swap phase label
            phase_labels = [l for l in current_labels if l.startswith("atdd:") and l != "atdd-issue"]
            if phase_labels:
                client.remove_label(issue_number, phase_labels)
            client.add_label(issue_number, [f"atdd:{status}"])

            # Update Project field
            if "ATDD: Status" in fields:
                options = fields["ATDD: Status"].get("options", {})
                if status in options:
                    client.set_project_field_select(
                        item_id, fields["ATDD: Status"]["id"], options[status]
                    )
            updated.append(f"status: {status}")

        # Phase (Planner/Tester/Coder)
        if phase:
            phase_cap = phase.capitalize()
            if "ATDD: Phase" in fields:
                options = fields["ATDD: Phase"].get("options", {})
                if phase_cap in options:
                    client.set_project_field_select(
                        item_id, fields["ATDD: Phase"]["id"], options[phase_cap]
                    )
                    updated.append(f"phase: {phase_cap}")
                else:
                    print(f"Warning: Unknown phase '{phase_cap}'")

        # Text fields
        text_updates = {
            "ATDD: Branch": branch,
            "ATDD: Train": train,
            "ATDD: Feature URN": feature_urn,
            "ATDD: Archetypes": archetypes,
        }
        for field_name, value in text_updates.items():
            if value and field_name in fields:
                client.set_project_field_text(item_id, fields[field_name]["id"], value)
                # Display the short name (strip "ATDD: " prefix)
                display_name = field_name.removeprefix("ATDD: ").lower()
                updated.append(f"{display_name}: {value}")

        # Complexity
        if complexity:
            if "ATDD: Complexity" in fields:
                options = fields["ATDD: Complexity"].get("options", {})
                if complexity in options:
                    client.set_project_field_select(
                        item_id, fields["ATDD: Complexity"]["id"], options[complexity]
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

    def close_wmbt(self, issue_id: str, wmbt_id: str, force: bool = False) -> int:
        """Close a WMBT sub-issue by ID."""
        if not self._check_initialized():
            return 1

        from atdd.coach.github import GitHubClientError

        try:
            issue_number = int(issue_id)
        except ValueError:
            print(f"Error: Invalid issue number '{issue_id}'")
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
        """Sync is a no-op in GitHub-only mode. Issues are the source of truth."""
        print("Sync not needed — GitHub Issues are the source of truth.")
        print("Use `atdd list` to see current issues.")
        return 0
