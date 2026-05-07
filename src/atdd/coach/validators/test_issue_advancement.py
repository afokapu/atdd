"""
Post-merge issue advancement validation.

Purpose: Flag merged PRs where the linked issue did not advance its ATDD
phase label.  This catches the incident pattern from #256: PRs merge but
issue stays at INIT, so skipped lifecycle phases go undetected.

SPEC-COACH-PRGATE-0003: Merged PR with linked issue that hasn't advanced
phase is flagged as stale.

Run: atdd validate coach
"""

import logging
from pathlib import Path
from typing import List, Sequence, Tuple

import pytest

from atdd.coach.commands.pr import PRManager
from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.repo import find_repo_root

pytestmark = [pytest.mark.platform, pytest.mark.github_api]

REPO_ROOT = find_repo_root()

# Phases that should have advanced after a PR merges.
# If a PR merged and the issue is still at one of these, something was missed.
_STALE_PHASES = frozenset({"INIT", "PLANNED"})

# Terminal or expected post-merge phases — no advancement expected
_TERMINAL_PHASES = frozenset({"COMPLETE", "OBSOLETE"})

# Issue labels that mark a non-lifecycle issue (parent meta-issue, tracker,
# milestone, etc.). These don't advance through the standard 6-phase lifecycle
# because their "advancement" is the cumulative state of their child issues,
# not a single phase transition. PRs that reference them (e.g., a docs PR whose
# title includes "(#406)") should not trigger advancement enforcement.
_NON_LIFECYCLE_LABELS = frozenset({"tracking", "meta", "epic", "parent"})


def _issue_is_non_lifecycle(issue_data: dict) -> bool:
    """True if the issue carries a label marking it as non-lifecycle."""
    labels = issue_data.get("labels", []) or []
    label_names = {
        (lbl.get("name") if isinstance(lbl, dict) else lbl)
        for lbl in labels
    }
    return bool(label_names & _NON_LIFECYCLE_LABELS)


def scan_issue_advancement(repo_root: Path) -> Tuple[int, Sequence]:
    """Scan recently merged PRs for stale linked issues.

    A merged PR whose linked issue is still at INIT or PLANNED indicates
    the issue phase was not advanced after the PR merged.

    Returns (violation_count, violation_messages) for ratchet baseline.
    """
    mgr = PRManager(target_dir=repo_root)
    merged_prs = mgr.fetch_recently_merged_prs(limit=20)
    violations: List[str] = []

    for pr in merged_prs:
        pr_number = pr["number"]
        resolution = mgr.resolve_linked_issue(pr_number)
        if resolution is None:
            continue

        phase = resolution["phase_label"]
        if phase is None:
            continue

        issue_number = resolution["issue_number"]
        issue_state = resolution["issue_data"].get("state", "").upper()

        # Skip closed issues — GitHub auto-close may have handled it
        if issue_state == "CLOSED":
            continue

        # Skip terminal phases
        if phase in _TERMINAL_PHASES:
            continue

        # Skip non-lifecycle issues (tracking / meta / epic / parent).
        # Their "advancement" is the cumulative state of child issues, not
        # a single label transition.
        if _issue_is_non_lifecycle(resolution["issue_data"]):
            continue

        if phase in _STALE_PHASES:
            merged_at = pr.get("mergedAt", "unknown")
            violations.append(
                f"PR #{pr_number} merged ({merged_at}) but linked issue "
                f"#{issue_number} is still at {phase} — expected phase "
                f"advancement after merge. "
                f"Fix: atdd issue {issue_number} --status <next-phase> "
                f'(e.g. "REFACTOR" or "COMPLETE"; '
                f"see CLAUDE.md::state_machine.transitions for the valid "
                f"transitions out of {phase})."
            )
            logging.getLogger(__name__).warning(
                "SPEC-COACH-PRGATE-0003: PR #%d merged but issue #%d "
                "still at %s",
                pr_number, issue_number, phase,
                extra={
                    "pr": pr_number,
                    "issue": issue_number,
                    "phase": phase,
                    "merged_at": merged_at,
                },
            )

    return len(violations), violations


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


def test_issue_advancement():
    """
    SPEC-COACH-PRGATE-0003: Linked issue must advance after PR merge.

    Given: Recently merged PRs with linked ATDD issues
    When: Checking the linked issue's current phase label
    Then: Issues still at INIT/PLANNED after PR merge are gated by
          COACH-PRGATE-0003's disposition.
    """
    _count, violations = scan_issue_advancement(REPO_ROOT)
    assert_disposition_satisfied(
        validator_id="issue_advancement",
        violations=violations,
    )
