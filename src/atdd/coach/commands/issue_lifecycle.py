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


def _check_on_main_branch(repo_root: Path) -> tuple:
    """Return (True, None) if current branch is main, else (False, error_message).

    Checks via `git rev-parse --abbrev-ref HEAD`. Returns (True, None) when git
    is unavailable so the check never blocks non-git test fixtures.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=10,
            cwd=repo_root,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        return True, None

    if result.returncode != 0:
        return True, None

    branch = result.stdout.strip()
    if not branch or branch == "HEAD":
        return True, None

    if branch == "main":
        return True, None

    msg = (
        f"Error: `atdd issue` must be run from the 'main' branch.\n"
        f"  Current branch: {branch}\n"
        f"  The manifest commit will land on '{branch}', not main.\n"
        f"  Fix:\n"
        f"    git checkout main\n"
        f"    atdd issue my-feature   # re-run with your slug\n"
        f"  Override: atdd issue my-feature --force   # re-run with your slug"
    )
    return False, msg

# Statuses from PLANNED onward require a template-compliant issue body.
_COMPLIANCE_REQUIRED_STATUSES = {"PLANNED", "RED", "GREEN", "SMOKE", "REFACTOR"}


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
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
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
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
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

        # Creation + I-1/I-2/I-9 incident defenses are owned by the runtime
        # layer (docs/coach-decomposition.md §13.5).
        from atdd.runtime import worktree as runtime_worktree
        if remote_exists:
            print(f"Attaching to existing remote branch: {branch_name}")
        else:
            print(f"Creating new branch: {branch_name}")

        try:
            created = runtime_worktree.ensure_issue_worktree(
                worktree_path, branch_name, self.target_dir,
                issue_number=issue_number,
            )
        except runtime_worktree.ProtectedBranchError as exc:
            logger.warning(
                "refused worktree on protected branch",
                extra={"issue": issue_number, "error": str(exc)},
            )
            print(f"Error: {exc}")
            return None
        if created is None:
            print("Error: git worktree add failed")
            return None

        print(f"  Worktree: {worktree_path}")

        # Branch lineage is recorded in the local manifest by ``atdd branch``
        # (#1051); the Projects v2 "ATDD Branch" field is decommissioned, so no
        # board write happens here.

        # Refresh workspace
        try:
            from atdd.coach.commands.initializer import write_workspace
            write_workspace(self.target_dir)
        except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
            pass

        return worktree_path

    def _run_gate(self, worktree_path: Path) -> int:
        """Run ``atdd gate`` in the worktree for DISPLAY only (advisory).

        This prints the toolkit gate output when an agent enters a worktree; it
        is intentionally advisory and its return code is informational — the
        enter() caller does not act on it. Do NOT retrofit this into a blocker:
        the full ``atdd gate`` advisory output gates nothing on purpose, because
        hard-blocking on it would brick every in-flight transition (#1020 scope
        E migration-safety).

        The ENFORCING per-transition chokepoint is ``_transition_gate`` (called
        from ``transition()``), which acts on a fail-closed verdict from the
        pure ``atdd.coach.gate`` decision module against the per-transition check
        registry. That is where "act on the return code, never swallow it" lives.
        """
        try:
            result = subprocess.run(
                ["atdd", "gate"],
                capture_output=True, text=True, timeout=30,
                cwd=worktree_path,
            )
            if result.stdout:
                print(result.stdout.rstrip())
            return result.returncode
        except (subprocess.TimeoutExpired, FileNotFoundError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
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

    def check(self, issue_number: int) -> int:
        """Run template compliance check against an issue body.

        Returns 0 if compliant, 1 if missing sections or placeholders remain.

        SPEC-COACH-ORCH-0010: structured section-by-section feedback.
        """
        from atdd.coach.commands.issue_template import check_issue_compliance

        issue = self._fetch_issue(issue_number)
        if not issue:
            print(f"❌ could not fetch issue #{issue_number}")
            return 1
        report = check_issue_compliance(
            issue_number=issue_number,
            body=issue.get("body") or "",
        )
        print(report.format())
        return 0 if report.compliant else 1

    def _compliance_gate(self, issue_number: int, target_status: str) -> int:
        """Block transitions to PLANNED+ on non-compliant issue bodies.

        SPEC-COACH-ORCH-0011: PLANNED and beyond require all template
        sections + no leftover placeholders.
        """
        if target_status.upper() not in _COMPLIANCE_REQUIRED_STATUSES:
            return 0
        from atdd.coach.commands.issue_template import check_issue_compliance

        issue = self._fetch_issue(issue_number)
        if not issue:
            print(f"❌ could not fetch issue #{issue_number} for compliance check")
            return 1
        report = check_issue_compliance(
            issue_number=issue_number,
            body=issue.get("body") or "",
        )
        if report.compliant:
            return 0
        print(report.format())
        print(
            f"\nTransition to {target_status.upper()} blocked by template "
            f"compliance gate. Re-run with --force to override."
        )
        return 1

    def _load_config(self) -> dict:
        """Read .atdd/config.yaml as a dict (empty dict when absent/unreadable)."""
        import yaml
        if not self.config_file.exists():
            return {}
        try:
            return yaml.safe_load(self.config_file.read_text()) or {}
        except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-09-01
            return {}

    def _transition_gate(self, issue_number: int, target_status: str,
                         force: bool = False) -> int:
        """Enforcing per-transition gate — the keystone chokepoint (#1020).

        Thin caller of the pure ``atdd.coach.gate`` decision module: resolves the
        checks registered for the ``current_phase -> target_status`` transition
        and BLOCKS (returns non-zero, so transition() never reaches
        IssueManager.update()'s label/phase swap) when any check fails.
        Fail-closed: an errored/timed-out check counts as a failure.

        Migration-safe by construction: ``GATE_REGISTRY`` ships empty, so every
        transition is a no-op here until #958/#1017 register real checks. ``force``
        bypasses with a loud warning, mirroring the other transition gates.
        """
        from atdd.coach.gate.decision import GateContext, evaluate_transition_gate
        from atdd.coach.gate.registry import GATE_REGISTRY

        # Fast path + migration safety: an empty registry can never block, so
        # skip the gate (and its issue fetch) entirely until checks are
        # registered (#958/#1017). This keeps the shipped behavior a true no-op.
        if GATE_REGISTRY.is_empty():
            return 0

        issue = self._fetch_issue(issue_number)
        if not issue:
            print(f"❌ could not fetch issue #{issue_number} for transition gate")
            return 1
        from_phase = self._get_status_from_labels(issue.get("labels", []))
        ctx = GateContext(
            issue_number=issue_number,
            from_phase=from_phase,
            to_phase=target_status.upper(),
            worktree=self.target_dir,
        )
        outcome = evaluate_transition_gate(GATE_REGISTRY, self._load_config(), ctx)
        if outcome.proceed:
            return 0

        if force:
            print(
                f"::warning::Transition gate bypassed (--force) for "
                f"{from_phase} -> {target_status.upper()}; "
                f"{len(outcome.failures)} check(s) failed."
            )
            return 0

        print(
            f"\nError: Transition {from_phase} -> {target_status.upper()} blocked "
            f"by {len(outcome.failures)} failing gate check(s):"
        )
        for f in outcome.failures:
            print(f"  ✗ [{f.gate_id} / {f.rule_id}] {f.message}")
        print(f"  Bypass: atdd issue {issue_number} --status {target_status.upper()} --force")
        return 1

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

        # Enforcing per-transition gate — the #1020 keystone. Acts on the gate
        # verdict (unlike the advisory _run_gate it replaces): a failing
        # registered check returns non-zero here, so we never reach
        # IssueManager.update()'s label/phase swap. Empty registry => no-op.
        gate_rc = self._transition_gate(issue_number, status, force=force)
        if gate_rc != 0:
            return gate_rc

        # Template compliance gate — PLANNED and beyond require a fully
        # populated issue body (SPEC-COACH-ORCH-0011). --force overrides.
        if not force:
            gate_rc = self._compliance_gate(issue_number, status)
            if gate_rc != 0:
                return gate_rc

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

        # R002: re-enter in display-only mode so the post-transition path does
        # not attempt to create a worktree branch (and therefore cannot fail on
        # the branch-creation layout check). The transition itself already
        # landed — all the re-enter step needs to do is print updated state.
        return self._reenter_display_only(issue_number)

    def _reenter_display_only(self, issue_number: int) -> int:
        """Print the current state of an issue without touching worktrees.

        Used as the tail step of transition() so a successful GitHub update is
        never masked by a misleading ``Repository layout is 'worktree', expected
        'worktree-ready'`` error coming from the branch-creation path.
        """
        issue = self._fetch_issue(issue_number)
        if not issue:
            print(f"Error: Could not fetch issue #{issue_number}")
            return 1

        labels = issue.get("labels", [])
        status = self._get_status_from_labels(labels)
        slug, prefix = self._get_slug_and_prefix(issue)
        sub_issues = self._fetch_sub_issues(issue_number, slug)

        self._print_context(issue, status, sub_issues, slug, prefix, None)
        return 0

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
               train: Optional[str] = None, archetypes: Optional[str] = None,
               no_branch: bool = False, force: bool = False,
               no_dup_check: bool = False) -> int:
        """Create a new issue, optionally chain to worktree creation, and enter at INIT.

        Delegates to IssueManager.new() for creation (slugify, template rendering,
        WMBT sub-issues, Project v2 fields, manifest update), then reads manifest
        to discover the created issue number and enters it.

        Args:
            slug: Issue name in kebab-case.
            issue_type: Issue type (implementation, migration, refactor, etc.).
            train: Optional train ID to assign.
            archetypes: Optional comma-separated archetypes.
            no_branch: When True, skip worktree creation (bare issue-only mode).
            force: When True, bypass the main-branch check.

        Returns:
            0 on success, 1 on failure.
        """
        import yaml
        from atdd.coach.commands.issue import IssueManager

        # Phase 1: guard — manifest commit must land on main.
        on_main, branch_error = _check_on_main_branch(self.target_dir)
        if not on_main:
            if not force:
                print(branch_error)
                return 1
            print(f"Warning: proceeding off main (--force). {branch_error.splitlines()[0]}")

        manager = IssueManager(self.target_dir)
        rc = manager.new(
            slug=slug,
            issue_type=issue_type,
            train=train,
            archetypes=archetypes,
            allow_main_commit=True,
            no_dup_check=no_dup_check,
        )
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
        from atdd.coach.commands.issue import IssueManager as _IM
        slugified = _IM(self.target_dir)._slugify(slug)

        issue_number = None
        for entry in reversed(sessions):
            if entry.get("slug") == slugified:
                issue_number = entry.get("issue_number")
                break

        if not issue_number:
            print(f"Error: Could not find issue number for slug '{slug}' in manifest.")
            return 1

        # Phase 2: chain to worktree creation (default) or print intent (--no-branch).
        from atdd.coach.commands.issue import TYPE_TO_PREFIX
        prefix = TYPE_TO_PREFIX.get(issue_type, "feat")

        if not no_branch:
            worktree_path = self._create_branch(issue_number, slugified, prefix)
            if worktree_path:
                print(f"  ✓ created at {worktree_path}")
            else:
                print(
                    f"  (worktree creation failed — run `atdd branch {issue_number}` when ready)"
                )
        else:
            print(
                f"  (not created — run `atdd branch {issue_number}` when ready)"
            )

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
                self._run_gate(worktree_path)
                self._print_context(issue, status, sub_issues, slug, prefix, worktree_path)
                return 0

            # Not in correct worktree — find or create, then hard handoff
            existing = self._find_worktree_for_issue(slug, prefix)
            if existing:
                worktree_path = existing
            else:
                worktree_path = self._create_branch(issue_number, slug, prefix)
                if not worktree_path:
                    print("Error: Failed to create worktree branch.")
                    return 1

            # Hard handoff — stop here, do not run gate or print full context
            print()
            print(f"ATDD: Issue #{issue_number} requires worktree: {prefix}/{slug}")
            print(f"  cd {worktree_path}")
            print(f"  atdd issue {issue_number}")
            print()
            return 0

        # Print context (INIT, UNKNOWN, etc.)
        self._print_context(issue, status, sub_issues, slug, prefix, worktree_path)
        return 0
