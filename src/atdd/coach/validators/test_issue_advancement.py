"""
Post-merge issue advancement validation.

Purpose: Flag merged PRs where the linked issue did not advance its ATDD
phase label.  This catches the incident pattern from #256: PRs merge but
issue stays at INIT, so skipped lifecycle phases go undetected.

SPEC-COACH-PRGATE-0003: Merged PR with linked issue that hasn't advanced
phase is flagged as stale.

Scope (issue #1296): the BLOCKING signal is confined to the PR *under
validation* — its own linked issue, resolved deterministically from the CI
environment (``GITHUB_REF``/``GITHUB_HEAD_REF``) or the current branch's PR.
The historical behaviour of sweeping the last ~20 merged PRs' *live* issue
phases is retained only as a non-blocking ADVISORY (logged warnings): it
still surfaces stale hygiene, but it can no longer couple an unrelated PR —
or the release commit — to another issue that is momentarily at INIT/PLANNED.
That cross-PR sweep was the #1172/#1274/#1285 whack-a-mole: it is inherently
non-deterministic (window + live state), so it must never gate CI.

Run: atdd validate coach
"""

import logging
import os
import re
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

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


# Regex for a PR number embedded in an env ref or a PR URL.
_PULL_REF_RE = re.compile(r"refs/pull/(\d+)/")
_PULL_URL_RE = re.compile(r"/pull/(\d+)")


def _current_pr_number(mgr: "PRManager") -> Optional[int]:
    """Resolve the PR under validation, deterministically and best-effort.

    Resolution order (first hit wins):
        1. ``GITHUB_REF`` — PR-triggered CI sets ``refs/pull/<N>/merge`` (or
           ``.../head``); parsed without any network call.
        2. ``GITHUB_PR_NUMBER`` / ``PR_NUMBER`` — explicit env overrides.
        3. The current branch (``GITHUB_HEAD_REF`` or the detected git
           branch) → its open, then merged, PR via the ``gh`` CLI.

    Returns None when no single PR is in scope (e.g. a local
    ``atdd validate coach`` run not tied to one PR). A None result means the
    blocking path finds nothing — the gate stays deterministically green.
    """
    ref = os.environ.get("GITHUB_REF", "")
    match = _PULL_REF_RE.search(ref)
    if match:
        return int(match.group(1))

    for var in ("GITHUB_PR_NUMBER", "PR_NUMBER"):
        val = os.environ.get(var, "").strip()
        if val.isdigit():
            return int(val)

    branch = os.environ.get("GITHUB_HEAD_REF") or mgr._detect_branch()
    if not branch:
        return None
    for resolver in (mgr._existing_pr_for_branch, mgr._merged_pr_for_branch):
        url = resolver(branch)
        if url:
            url_match = _PULL_URL_RE.search(url)
            if url_match:
                return int(url_match.group(1))
    return None


def _evaluate_pr(mgr: "PRManager", pr: dict) -> Optional[str]:
    """Return a staleness violation message for ``pr``, or None if fine.

    Shared by the blocking own-PR check and the advisory cross-PR sweep so
    both apply the identical skip logic (closed / terminal / non-lifecycle).
    ``pr`` needs a ``number`` key; ``mergedAt`` is used for the message when
    present.
    """
    pr_number = pr["number"]
    resolution = mgr.resolve_linked_issue(pr_number)
    if resolution is None:
        return None

    phase = resolution["phase_label"]
    if phase is None:
        return None

    issue_number = resolution["issue_number"]
    issue_state = resolution["issue_data"].get("state", "").upper()

    # Skip closed issues — GitHub auto-close may have handled it
    if issue_state == "CLOSED":
        return None

    # Skip terminal phases
    if phase in _TERMINAL_PHASES:
        return None

    # Skip non-lifecycle issues (tracking / meta / epic / parent). Their
    # "advancement" is the cumulative state of child issues, not a single
    # label transition.
    if _issue_is_non_lifecycle(resolution["issue_data"]):
        return None

    if phase in _STALE_PHASES:
        merged_at = pr.get("mergedAt", "unknown")
        return (
            f"PR #{pr_number} merged ({merged_at}) but linked issue "
            f"#{issue_number} is still at {phase} — expected phase "
            f"advancement after merge. "
            f"Fix: atdd coach transition {issue_number} <next-phase> "
            f'(e.g. "REFACTOR" or "COMPLETE"; '
            f"see CLAUDE.md::state_machine.transitions for the valid "
            f"transitions out of {phase})."
        )
    return None


def _advisory_cross_pr_sweep(
    mgr: "PRManager", own_pr: Optional[int]
) -> List[str]:
    """Log — never gate — stale linked issues across recently merged PRs.

    This preserves the historical hygiene signal without coupling the gate
    to unrelated, non-deterministic live issue state. Best-effort: any API
    failure degrades to an empty result rather than raising. The own PR (if
    any) is skipped here — it is enforced by the blocking path.
    """
    advisories: List[str] = []
    try:
        merged_prs = mgr.fetch_recently_merged_prs(limit=20)
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-09-01
        return advisories

    log = logging.getLogger(__name__)
    for pr in merged_prs:
        if own_pr is not None and pr.get("number") == own_pr:
            continue
        message = _evaluate_pr(mgr, pr)
        if message:
            advisories.append(message)
            log.warning(
                "SPEC-COACH-PRGATE-0003 [advisory, non-blocking]: %s",
                message,
                extra={"pr": pr.get("number"), "advisory": True},
            )
    return advisories


def scan_issue_advancement(repo_root: Path) -> Tuple[int, Sequence]:
    """Scan for stale linked issues, scoped to the PR under validation.

    BLOCKING signal: the current PR's own linked issue. If it is still at
    INIT/PLANNED, that is a deterministic own-PR violation (depends only on
    this PR's issue, not on unrelated hygiene).

    ADVISORY signal: the last ~20 merged PRs are still swept, but only to
    emit non-blocking warnings — they are NOT returned to the gate, so they
    can never fail CI on another issue that is momentarily at INIT/PLANNED.

    Returns (violation_count, violation_messages) for the disposition gate.
    """
    mgr = PRManager(target_dir=repo_root)
    violations: List[str] = []

    own_pr = _current_pr_number(mgr)
    if own_pr is not None:
        message = _evaluate_pr(mgr, {"number": own_pr})
        if message:
            violations.append(message)
            logging.getLogger(__name__).warning(
                "SPEC-COACH-PRGATE-0003: own PR #%d linked issue not advanced",
                own_pr,
                extra={"pr": own_pr},
            )

    # Non-blocking hygiene sweep over other recently merged PRs.
    _advisory_cross_pr_sweep(mgr, own_pr)

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
