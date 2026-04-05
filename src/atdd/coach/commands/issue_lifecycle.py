"""
Unified issue lifecycle command for ATDD.

Single orchestrator for the entire issue lifecycle:
- `atdd issue <N>` — enter an existing issue (state-driven behavior)
- `atdd issue <slug>` — create a new issue and enter at INIT
- `atdd issue <N> --status <STATUS>` — transition status
- `atdd issue <N> --close-wmbt <ID>` — close WMBT sub-issue

State-driven behavior for `atdd issue <N>`:
    INIT              → print context only (no branch)
    PLANNED and above → create/verify worktree branch, run gate, print context
    COMPLETE/OBSOLETE → print context, warn closed

Convention: src/atdd/coach/conventions/issue.convention.yaml
"""
import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Statuses where branch + gate are triggered
_BRANCH_STATUSES = {"PLANNED", "RED", "GREEN", "SMOKE", "REFACTOR", "BLOCKED"}
_TERMINAL_STATUSES = {"COMPLETE", "OBSOLETE"}


class IssueLifecycle:
    """Unified issue lifecycle orchestrator."""

    def __init__(self, target_dir: Optional[Path] = None):
        self.target_dir = target_dir or Path.cwd()
        self.atdd_config_dir = self.target_dir / ".atdd"
        self.config_file = self.atdd_config_dir / "config.yaml"

    def _get_repo(self) -> Optional[str]:
        """Read repo from .atdd/config.yaml."""
        import yaml
        if not self.config_file.exists():
            return None
        cfg = yaml.safe_load(self.config_file.read_text()) or {}
        return cfg.get("github", {}).get("repo")

    def _fetch_issue(self, issue_number: int) -> Optional[dict]:
        """Fetch issue metadata via gh CLI."""
        try:
            result = subprocess.run(
                ["gh", "issue", "view", str(issue_number),
                 "--json", "number,title,state,labels,body"],
                capture_output=True, text=True, timeout=15,
                cwd=self.target_dir,
            )
            if result.returncode != 0:
                return None
            import json
            return json.loads(result.stdout)
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
            return None

    def _fetch_sub_issues(self, issue_number: int, slug: str) -> list:
        """Fetch WMBT sub-issues for this parent issue.

        Matches by slug in WMBT title (wmbt:<slug>:<ID>) or by #N reference.
        """
        repo = self._get_repo()
        if not repo:
            return []
        try:
            # Search for WMBTs mentioning this slug in title
            result = subprocess.run(
                ["gh", "issue", "list", "--repo", repo,
                 "--label", "atdd-wmbt", "--state", "all",
                 "--search", f"wmbt:{slug} in:title",
                 "--json", "number,title,state",
                 "--limit", "50"],
                capture_output=True, text=True, timeout=15,
                cwd=self.target_dir,
            )
            if result.returncode != 0:
                return []
            import json
            return json.loads(result.stdout)
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
            return []

    def _get_status_from_labels(self, labels: list) -> str:
        """Extract ATDD status from issue labels."""
        for label in labels:
            name = label.get("name", "") if isinstance(label, dict) else str(label)
            if name.startswith("atdd:") and name != "atdd-issue":
                return name.split(":")[1].upper()
        return "UNKNOWN"

    def _get_branch_from_body(self, body: str) -> Optional[str]:
        """Extract branch hint from issue body metadata table.

        Looks for the fmt comment: <!-- fmt: feat/issue-lifecycle -->
        Falls back to the Branch field value if not TBD.
        """
        import re
        # Try fmt comment first: <!-- fmt: feat/my-slug -->
        m = re.search(r'<!--\s*fmt:\s*(\S+)\s*-->', body)
        if m:
            return m.group(1)
        # Fallback: Branch field value (if not TBD)
        m = re.search(r'\|\s*Branch\s*\|\s*([^|]+)', body)
        if m:
            value = m.group(1).strip()
            if value and value.upper() != "TBD" and "fmt:" not in value:
                return value
        return None

    def _parse_branch(self, branch: str) -> tuple:
        """Parse branch like 'feat/issue-lifecycle' into (prefix, slug)."""
        if "/" in branch:
            prefix, slug = branch.split("/", 1)
            return prefix, slug
        return "feat", branch

    def _get_slug_and_prefix(self, issue: dict) -> tuple:
        """Derive slug and prefix from issue body branch hint, falling back to title.

        Returns:
            (slug, prefix) tuple.
        """
        import re
        body = issue.get("body", "") or ""
        title = issue.get("title", "")

        # Try branch hint from body
        branch = self._get_branch_from_body(body)
        if branch:
            prefix, slug = self._parse_branch(branch)
            return slug, prefix

        # Fallback: derive from title
        m = re.match(r'^(feat|fix|refactor|chore|docs|devops)\([^)]+\):\s*(.+)$', title)
        if m:
            prefix = m.group(1)
            raw = m.group(2).strip()
            slug = re.sub(r'[^a-zA-Z0-9]+', '-', raw).strip('-').lower()
            return slug, prefix

        # Last resort
        return f"issue-{issue['number']}", "feat"

    def _find_worktree_for_issue(self, slug: str, prefix: str) -> Optional[Path]:
        """Check if a worktree already exists for this issue's branch."""
        worktree_dir_name = f"{prefix}-{slug}"
        worktree_path = self.target_dir.parent / worktree_dir_name
        if worktree_path.exists():
            return worktree_path
        return None

    def _is_in_worktree(self, slug: str, prefix: str) -> bool:
        """Check if we're currently in the correct worktree."""
        expected_dir_name = f"{prefix}-{slug}"
        return self.target_dir.name == expected_dir_name

    def _create_branch(self, issue_number: int, slug: str, prefix: str) -> Optional[Path]:
        """Create worktree branch. Returns worktree path or None on failure."""
        from atdd.coach.commands.branch import BranchManager
        manager = BranchManager(self.target_dir)
        entry = manager._find_issue(issue_number)
        if entry:
            rc = manager.branch(issue_number)
            if rc == 0:
                return self.target_dir.parent / f"{prefix}-{slug}"
            return None
        # If not in manifest, create worktree directly
        branch_name = f"{prefix}/{slug}"
        worktree_path = self.target_dir.parent / f"{prefix}-{slug}"
        if worktree_path.exists():
            return worktree_path

        # Fetch and check remote
        subprocess.run(
            ["git", "fetch", "origin"],
            capture_output=True, text=True, timeout=30,
            cwd=self.target_dir,
        )
        result = subprocess.run(
            ["git", "branch", "-r", "--list", f"origin/{branch_name}"],
            capture_output=True, text=True, timeout=10,
            cwd=self.target_dir,
        )
        remote_exists = bool(result.stdout.strip())

        if remote_exists:
            cmd = ["git", "worktree", "add", str(worktree_path), f"origin/{branch_name}"]
            print(f"Attaching to existing remote branch: {branch_name}")
        else:
            cmd = ["git", "worktree", "add", str(worktree_path), "-b", branch_name]
            print(f"Creating new branch: {branch_name}")

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
            cwd=self.target_dir,
        )
        if result.returncode != 0:
            print(f"Error: git worktree add failed:\n{result.stderr.strip()}")
            return None

        print(f"  Worktree: {worktree_path}")

        # Update GitHub ATDD Branch field
        try:
            import yaml
            from atdd.coach.github import GitHubClient, ProjectConfig
            proj = ProjectConfig.from_config(self.config_file)
            client = GitHubClient(repo=proj.repo, project_id=proj.project_id)
            item_id = client.get_project_item_id(issue_number)
            if item_id:
                fields = client.get_project_fields()
                if "ATDD Branch" in fields:
                    client.set_project_field_text(
                        item_id, fields["ATDD Branch"]["id"], branch_name,
                    )
                    print(f"  Updated ATDD Branch -> {branch_name}")
        except Exception as e:
            logger.debug("Could not update Branch field: %s", e, extra={"error": str(e)})

        # Refresh workspace
        try:
            from atdd.coach.commands.initializer import write_workspace
            write_workspace(self.target_dir)
        except Exception:
            pass

        return worktree_path

    def _run_gate(self, worktree_path: Path) -> int:
        """Run atdd gate in the worktree."""
        try:
            result = subprocess.run(
                ["atdd", "gate"],
                capture_output=True, text=True, timeout=30,
                cwd=worktree_path,
            )
            if result.stdout:
                print(result.stdout.rstrip())
            return result.returncode
        except (subprocess.TimeoutExpired, FileNotFoundError):
            print("Warning: Could not run atdd gate")
            return 0

    def _print_context(self, issue: dict, status: str, sub_issues: list,
                       slug: Optional[str], prefix: str,
                       worktree_path: Optional[Path]) -> None:
        """Print structured issue context as mandatory tool output."""
        number = issue["number"]
        title = issue["title"]

        print()
        print("=" * 70)
        print(f"ATDD Issue #{number}: {title}")
        print("=" * 70)
        print(f"  Status:  {status}")
        print(f"  State:   {issue.get('state', 'UNKNOWN')}")
        if slug and prefix:
            print(f"  Branch:  {prefix}/{slug}")
        if worktree_path:
            print(f"  Worktree: {worktree_path}")

        # WMBTs
        if sub_issues:
            open_wmbts = [w for w in sub_issues if w.get("state") == "OPEN"]
            closed_wmbts = [w for w in sub_issues if w.get("state") == "CLOSED"]
            print(f"\n  WMBTs: {len(open_wmbts)} open, {len(closed_wmbts)} closed")
            for w in sorted(sub_issues, key=lambda x: x["number"]):
                marker = "[ ]" if w.get("state") == "OPEN" else "[x]"
                print(f"    {marker} #{w['number']} {w['title'][:60]}")
        else:
            print("\n  WMBTs: none found")

        # Next action
        print()
        if status == "INIT":
            print("  Next: Fill issue scope, then transition:")
            print(f"         atdd issue {number} --status PLANNED")
        elif status == "PLANNED":
            print("  Next: Write failing tests (RED phase), then transition:")
            print(f"         atdd issue {number} --status RED")
        elif status == "RED":
            print("  Next: Implement to make tests pass (GREEN), then transition:")
            print(f"         atdd issue {number} --status GREEN")
        elif status == "GREEN":
            print("  Next: Run tester SMOKE verification, then transition:")
            print(f"         atdd issue {number} --status SMOKE")
        elif status == "SMOKE":
            print("  Next: Refactor to clean architecture, then transition:")
            print(f"         atdd issue {number} --status REFACTOR")
        elif status == "REFACTOR":
            print("  Next: Complete and close:")
            print(f"         atdd issue {number} --status COMPLETE")
        elif status in _TERMINAL_STATUSES:
            print(f"  This issue is {status}. No further action needed.")
        elif status == "BLOCKED":
            print("  This issue is BLOCKED. Resolve blockers, then transition back.")
        print("=" * 70)
        print()

    def transition(self, issue_number: int, status: str, force: bool = False) -> int:
        """Transition an issue to a new status, then re-enter to show updated state.

        Delegates to IssueManager.update() for state machine validation, train
        enforcement, COMPLETE gates, label swapping, and Project field updates.
        If status is COMPLETE, also calls IssueManager.archive() to auto-close
        WMBTs and the parent issue.

        Args:
            issue_number: GitHub issue number.
            status: Target status (e.g., PLANNED, RED, GREEN, SMOKE, REFACTOR, COMPLETE).
            force: Bypass gate/body checks (train still enforced).

        Returns:
            0 on success, 1 on failure.
        """
        from atdd.coach.commands.issue import IssueManager

        manager = IssueManager(self.target_dir)
        issue_id = str(issue_number)

        rc = manager.update(
            issue_id=issue_id,
            status=status,
            force=force,
        )
        if rc != 0:
            return rc

        # COMPLETE auto-archives: close WMBTs + parent issue
        if status.upper() == "COMPLETE":
            arc_rc = manager.archive(issue_id=issue_id)
            if arc_rc != 0:
                print(f"Warning: Archive step returned {arc_rc} after COMPLETE transition.")

        # Re-enter to show updated state
        return self.enter(issue_number)

    def close_wmbt(self, issue_number: int, wmbt_id: str, force: bool = False) -> int:
        """Close a WMBT sub-issue, then re-enter to show updated state.

        Delegates to IssueManager.close_wmbt() for the actual close logic.

        Args:
            issue_number: GitHub issue number (parent).
            wmbt_id: WMBT identifier (e.g., E001, D003).
            force: Close even if ATDD cycle checkboxes are unchecked.

        Returns:
            0 on success, 1 on failure.
        """
        from atdd.coach.commands.issue import IssueManager

        manager = IssueManager(self.target_dir)
        issue_id = str(issue_number)

        rc = manager.close_wmbt(
            issue_id=issue_id,
            wmbt_id=wmbt_id,
            force=force,
        )
        if rc != 0:
            return rc

        # Re-enter to show updated state
        return self.enter(issue_number)

    def create(self, slug: str, issue_type: str = "implementation",
               train: Optional[str] = None, archetypes: Optional[str] = None) -> int:
        """Create a new issue and enter it at INIT.

        Delegates to IssueManager.new() for creation (slugify, template rendering,
        WMBT sub-issues, Project v2 fields, manifest update), then reads manifest
        to discover the created issue number and enters it.

        Args:
            slug: Issue name in kebab-case.
            issue_type: Issue type (implementation, migration, refactor, etc.).
            train: Optional train ID to assign.
            archetypes: Optional comma-separated archetypes.

        Returns:
            0 on success, 1 on failure.
        """
        import yaml
        from atdd.coach.commands.issue import IssueManager

        manager = IssueManager(self.target_dir)
        rc = manager.new(slug=slug, issue_type=issue_type, train=train, archetypes=archetypes)
        if rc != 0:
            return rc

        # Read manifest to find the created issue number by slug
        manifest_path = self.atdd_config_dir / "manifest.yaml"
        if not manifest_path.exists():
            print("Error: manifest.yaml not found after creation.")
            return 1

        manifest = yaml.safe_load(manifest_path.read_text()) or {}
        sessions = manifest.get("sessions", [])

        # Find the entry matching our slug (last match in case of duplicates)
        issue_number = None
        for entry in reversed(sessions):
            if entry.get("slug") == slug:
                issue_number = entry.get("issue_number")
                break

        if not issue_number:
            print(f"Error: Could not find issue number for slug '{slug}' in manifest.")
            return 1

        # Enter the newly created issue at INIT
        return self.enter(issue_number)

    def enter(self, issue_number: int) -> int:
        """Enter an existing issue with state-driven behavior.

        Args:
            issue_number: GitHub issue number.

        Returns:
            0 on success, 1 on error.
        """
        # Fetch issue
        issue = self._fetch_issue(issue_number)
        if not issue:
            print(f"Error: Could not fetch issue #{issue_number}")
            print("Check that `gh` is authenticated and the issue exists.")
            return 1

        # Extract metadata
        labels = issue.get("labels", [])
        status = self._get_status_from_labels(labels)
        slug, prefix = self._get_slug_and_prefix(issue)

        # Fetch sub-issues (WMBTs)
        sub_issues = self._fetch_sub_issues(issue_number, slug)

        worktree_path = None

        if status in _TERMINAL_STATUSES:
            # Closed issue — just print context
            self._print_context(issue, status, sub_issues, slug, prefix, None)
            return 0

        if status == "INIT":
            # Still scoping — no branch needed
            self._print_context(issue, status, sub_issues, slug, prefix, None)
            return 0

        if status in _BRANCH_STATUSES:
            # Check if already in correct worktree
            if self._is_in_worktree(slug, prefix):
                worktree_path = self.target_dir
            else:
                # Check if worktree exists
                existing = self._find_worktree_for_issue(slug, prefix)
                if existing:
                    worktree_path = existing
                    print(f"Worktree exists: {worktree_path}")
                    print(f"  cd {worktree_path}")
                else:
                    # Create branch
                    worktree_path = self._create_branch(issue_number, slug, prefix)
                    if not worktree_path:
                        print("Error: Failed to create worktree branch.")
                        return 1

            # Run gate
            self._run_gate(worktree_path)

        # Print context
        self._print_context(issue, status, sub_issues, slug, prefix, worktree_path)
        return 0
