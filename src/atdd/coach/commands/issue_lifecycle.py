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


# Statuses from PLANNED onward require a template-compliant issue body.
_COMPLIANCE_REQUIRED_STATUSES = {"PLANNED", "RED", "GREEN", "SMOKE", "REFACTOR"}


# The per-phase "Next:" hint, as DATA. `{number}` is the issue number.
#
# REFACTOR is the one advance an operator normally does NOT type:
# .github/workflows/atdd-auto-phase.yml (#355) drives REFACTOR->COMPLETE from
# `pull_request: closed` + merged == true, through `atdd coach transition` ->
# IssueManager.update, so the store is written first and the atdd:<PHASE> label
# is projected from it. Printing only the manual command reads as an instruction
# and invites a hand-typed transition that races the workflow — the desync #1452
# removed the raw label-write from post-merge-lifecycle.yml to stop. Name the
# automatic path first, and keep the manual one for the cases that genuinely
# need it (no PR, or auto-phase did not run — e.g. #1621).
_NEXT_ACTION_HINTS = {
    "INIT": (
        "  Next: Fill issue scope, then transition:",
        "         atdd coach transition {number} PLANNED",
    ),
    "PLANNED": (
        "  Next: Write failing tests (RED phase), then transition:",
        "         atdd coach transition {number} RED",
    ),
    "RED": (
        "  Next: Implement to make tests pass (GREEN), then transition:",
        "         atdd coach transition {number} GREEN",
    ),
    "GREEN": (
        "  Next: Run tester SMOKE verification, then transition:",
        "         atdd coach transition {number} SMOKE",
    ),
    "SMOKE": (
        "  Next: Refactor to clean architecture, then transition:",
        "         atdd coach transition {number} REFACTOR",
    ),
    "REFACTOR": (
        "  Next: Merge the PR — REFACTOR → COMPLETE is automatic:",
        "         .github/workflows/atdd-auto-phase.yml advances the",
        "         phase on merge and projects the label from the store.",
        "  Manual (only if there is no PR, or auto-phase did not run):",
        "         atdd coach transition {number} COMPLETE",
    ),
    "COMPLETE": ("  This issue is COMPLETE. No further action needed.",),
    "OBSOLETE": ("  This issue is OBSOLETE. No further action needed.",),
    "BLOCKED": ("  This issue is BLOCKED. Resolve blockers, then transition back.",),
}



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
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
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
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
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
        except (subprocess.TimeoutExpired, FileNotFoundError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
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
        self._print_next_action(status, number)
        print("=" * 70)
        print()

    def _print_next_action(self, status: str, number: int) -> None:
        """Print the operator's next step for *status*.

        Table-driven rather than an if/elif chain (#1626): the hints are DATA,
        one entry per phase, so adding a phase is an entry here and the branch
        count does not grow with the phase machine.
        """
        for line in _NEXT_ACTION_HINTS.get(status, ()):
            print(line.format(number=number))

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
        print(f"  Bypass: atdd coach transition {issue_number} {target_status.upper()} --force")
        return 1

    def transition(self, issue_number: int, status: str, force: bool = False) -> int:
        """Transition an issue to a new status, then re-enter to show updated state.

        #1304: the orchestration was MOVED to
        :func:`atdd.coach.commands.issue_transition.apply_transition` (the home
        of ``atdd coach transition``); this method now delegates to it so the
        deprecated ``atdd update``/``atdd archive`` shims and the #1020/#1017
        gate tests keep running through the one implementation. The moved
        orchestration still delegates to ``IssueManager.update()`` for
        state-machine validation, train enforcement, COMPLETE gates, the github
        label swap, the store-first write, and the manifest mirror; COMPLETE
        also auto-archives.

        NOTE: this path intentionally does NOT register the operator-approval
        gate check — only the ``atdd coach transition`` verb (and the deprecated
        ``atdd issue --status`` shim that delegates to it) does. That preserves
        the historical behavior where ``atdd update``/``atdd archive`` never
        enforced the operator token.

        Args:
            issue_number: GitHub issue number.
            status: Target status (e.g., PLANNED, RED, GREEN, SMOKE, REFACTOR, COMPLETE).
            force: Bypass gate/body checks (train still enforced).

        Returns:
            0 on success, 1 on failure.
        """
        from atdd.coach.commands.issue_transition import apply_transition

        return apply_transition(
            issue_number, status, force=force, target_dir=self.target_dir
        )

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
            print(f"  atdd coach enter {issue_number}")
            print()
            return 0

        # Print context (INIT, UNKNOWN, etc.)
        self._print_context(issue, status, sub_issues, slug, prefix, worktree_path)
        return 0
