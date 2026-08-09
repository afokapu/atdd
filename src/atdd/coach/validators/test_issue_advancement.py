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

STATE ONLY WHAT WAS OBSERVED (issue #1748). The blocking path called
``_evaluate_pr(mgr, {"number": own_pr})`` — a dict carrying nothing but the
number — and the message template then read ``pr.get("mergedAt", "unknown")``
into a sentence whose grammar already assumed the merge. So an OPEN PR was
reported as "PR #1743 merged (unknown)" while ``state=open merged=false
merged_at=null``, and the check FAILED on that invented fact. Three states —
merged, not merged, could not tell — were collapsed into a sentence that only
knew one, which is #1719's four-verdict problem in prose. The merge state is now
read (from the PR row, else from ``resolution["pr_data"]``), an unmerged PR owes
this rule nothing, and an indeterminate one reports could-not-check.

AND THE REMEDY COMES FROM THE PHASE MACHINE. The old ``Fix:`` line prescribed
``atdd coach transition <N> <next-phase> (e.g. "REFACTOR" or "COMPLETE")``.
Followed verbatim from PLANNED that drives an issue to a phase meaning
"implemented and verified" without RED, GREEN or SMOKE ever executing — a strict
gate whose own remedy defeats the lifecycle it polices. The next phase is now
derived from ``coach/conventions/phase_machine.convention.yaml``, the single
source of truth, so the remedy cannot name a phase the machine does not declare
reachable from where the issue actually stands.

Run: atdd validate coach
"""

import logging
import os
import re
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import pytest

from atdd.coach.commands.pr import PRManager
from atdd.coach.core import _NON_FORWARD_TARGETS
from atdd.coach.gate.decision import GateVerdict
from atdd.coach.gate.phase_edges import PhaseMachineUnavailable, phase_machine
from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.validators._observation import COULD_NOT_CHECK_PREFIX

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


#: PR ``state`` values that settle the merge question without a ``mergedAt``.
#: ``gh pr list --state merged`` returns ``MERGED``; ``gh pr view`` on a live PR
#: returns ``OPEN`` / ``CLOSED``. Anything else is left indeterminate rather than
#: guessed at, which is the whole point of #1748.
_MERGED_STATES = frozenset({"MERGED"})
_UNMERGED_STATES = frozenset({"OPEN", "CLOSED", "DRAFT"})

#: Escapes rather than forward progress. Imported from ``atdd.coach.core`` — the
#: repo's one Python home for this distinction — so the remedy does not grow a
#: second, drifting copy of "which targets are real advancement".
_ESCAPE_TARGETS = frozenset(p.value for p in _NON_FORWARD_TARGETS)


def _issue_is_non_lifecycle(issue_data: dict) -> bool:
    """True if the issue carries a label marking it as non-lifecycle."""
    labels = issue_data.get("labels", []) or []
    label_names = {
        (lbl.get("name") if isinstance(lbl, dict) else lbl)
        for lbl in labels
    }
    return bool(label_names & _NON_LIFECYCLE_LABELS)


def _merge_state(*sources: Optional[dict]) -> Optional[bool]:
    """Did this PR merge? ``True`` / ``False`` / ``None`` for "could not tell".

    ``sources`` are consulted in order — the PR row from
    ``fetch_recently_merged_prs`` first (it carries ``state`` and ``mergedAt``
    for the advisory sweep), then ``resolution["pr_data"]`` from ``_fetch_pr``
    (which carries both for the own-PR blocking path).

    Returns ``None`` rather than guessing when neither source says. That third
    answer is the one the old template could not spell: it read a missing
    ``mergedAt`` as "merged, date unclear" and printed ``merged (unknown)``.
    """
    for source in sources:
        if not isinstance(source, dict):
            continue
        if source.get("mergedAt"):
            return True
        state = str(source.get("state") or "").upper()
        if state in _MERGED_STATES:
            return True
        if state in _UNMERGED_STATES:
            return False
    return None


def next_phase_remedy(phase: str, issue_number: int) -> str:
    """The remedy sentence for an issue standing at ``phase``, from the machine.

    ``phase_machine()`` reads ``coach/conventions/phase_machine.convention.yaml``,
    which declares itself the single source of truth ("add or change a phase
    HERE, never in Python"). The forward target is the first declared transition
    that is not an escape — the same selection ``atdd.coach.core._forward_target``
    makes, on the same data.

    Never names a phase the machine does not declare reachable from ``phase``, so
    it cannot repeat the old hardcoded ``e.g. "REFACTOR" or "COMPLETE"`` that
    skipped RED, GREEN and SMOKE. When the machine cannot be read it names NO
    phase at all and points at the file — a remedy invented at the one moment the
    lifecycle is unreadable is exactly the fabrication this issue is about.
    """
    try:
        machine = phase_machine()
    except PhaseMachineUnavailable as exc:
        return (
            f"Fix: advance #{issue_number} to the next phase the lifecycle "
            f"declares after {phase} — this run could not read the phase machine "
            f"to name it ({exc}); "
            f"see src/atdd/coach/conventions/phase_machine.convention.yaml."
        )

    targets = machine.get(str(phase).upper(), ())
    forward = next((t for t in targets if t not in _ESCAPE_TARGETS), None)
    if forward is None:
        return (
            f"Fix: the phase machine declares no forward transition out of "
            f"{phase} for #{issue_number}; "
            f"see src/atdd/coach/conventions/phase_machine.convention.yaml."
        )
    return (
        f"Fix: run `atdd coach transition {issue_number} {forward}` — "
        f"{forward} is the phase the machine declares next after {phase} "
        f"(see src/atdd/coach/conventions/phase_machine.convention.yaml)."
    )


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
    ``pr`` needs a ``number`` key; ``state``/``mergedAt`` settle the merge
    question when present, and ``resolution["pr_data"]`` supplies them when the
    caller passed only a number.

    The message states what was observed and nothing else (#1748):

    * merged + issue at INIT/PLANNED → the real condition, reported as a merge.
    * NOT merged → ``None``. Nothing is owed before a merge; that is
      ``NOT_APPLICABLE``, and inventing a merge to fail on was the defect.
      A pre-SMOKE PR that should not merge is
      ``coach.pr.merge-blocks-on-pre-smoke-close``'s job, not this one's.
    * merge state indeterminate → ``COULD_NOT_CHECK``, which refuses. It says
      the state could not be read; it does not assert either answer.
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

    if phase not in _STALE_PHASES:
        return None

    merged = _merge_state(pr, resolution.get("pr_data"))
    if merged is False:
        return None
    if merged is None:
        return (
            f"{COULD_NOT_CHECK_PREFIX} PR #{pr_number}'s merge state could not be "
            f"read (no `state` and no `mergedAt` came back), so whether linked "
            f"issue #{issue_number} — currently at {phase} — owes an advancement "
            f"cannot be decided. Re-run once the API is reachable "
            f"(run `gh pr view {pr_number} --json state,mergedAt` to see what it "
            f"answers)."
        )

    merged_at = (pr.get("mergedAt") or (resolution.get("pr_data") or {}).get("mergedAt"))
    when = f" at {merged_at}" if merged_at else ""
    return (
        f"PR #{pr_number} merged{when} but linked issue #{issue_number} is still "
        f"at {phase} — expected phase advancement after merge. "
        f"{next_phase_remedy(phase, issue_number)}"
    )


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
    log = logging.getLogger(__name__)
    violations: List[str] = []

    own_pr = _current_pr_number(mgr)
    if own_pr is None:
        # Name the green. This rule is about a PR that MERGED; a run with no PR in
        # scope observed nothing and must say so rather than bank a silent pass
        # indistinguishable from a verified one (#1747's lesson, same family).
        log.info(
            "SPEC-COACH-PRGATE-0003: %s — no PR under validation on this run, so "
            "no post-merge advancement was checked",
            GateVerdict.NOT_APPLICABLE.value,
            extra={"verdict": GateVerdict.NOT_APPLICABLE.value},
        )
    else:
        message = _evaluate_pr(mgr, {"number": own_pr})
        if message:
            violations.append(message)
            log.warning(
                "SPEC-COACH-PRGATE-0003: own PR #%d — %s",
                own_pr, message,
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
