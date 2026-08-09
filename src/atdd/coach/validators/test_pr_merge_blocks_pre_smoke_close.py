# Acceptance: acc:govern-lifecycle:E003-INTEGRATION-002-coach-validator-fires-on-green-label-closes
# Acceptance: acc:govern-lifecycle:E003-INTEGRATION-003-pr-merge-passes-when-no-closes-reference
"""
coach.pr.merge-blocks-on-pre-smoke-close validator (issue #681).

Scans open PRs via PRManager and emits one structured Violation per PR
that auto-closes an ATDD issue still at a pre-SMOKE phase (RED/GREEN —
also INIT/PLANNED defensively).

Strict disposition — bypass forbidden; no inline suppression. The 2026-
05-13 substrate-asymmetry incident shipped 8 PRs whose ``Closes #N`` fired
at atdd:GREEN, skipping SMOKE+REFACTOR. This rule mirrors the tester-side
TESTER-SMOKE-PRES-001 pattern in coach.

AN UNREADABLE LINK REFUSES (#1747). ``PRManager.resolve_linked_issue``
answers ``None`` both when a PR declares no auto-closing reference and when
it declares one that could not be read, and this scanner used to ``continue``
past both — so a strict gate reported PASS on an observation it never made.
Measured on PR ``#1757``: head sha ``54bdad8af`` passed on the ``push`` run at
12:58:31Z and failed on the ``pull_request`` run at 13:08:46Z, two seconds
after the PR came into existence, from identical repository state. The two
cases are now separated by :func:`read_pr_issue_link` and the unreadable one
blocks — ``COULD_NOT_CHECK`` in #1719's vocabulary, which refuses. A PR that
declares no auto-close is still ``NOT_APPLICABLE`` and still merges.

Convention: ``src/atdd/coach/conventions/pr.convention.yaml``
            (rule ``coach.pr.merge-blocks-on-pre-smoke-close``).

Run: ``atdd validate coach``
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, List, Optional, Sequence

import pytest

from atdd.coach.commands.pr import PRManager
from atdd.coach.gate.decision import GateVerdict
from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._observation import (
    COULD_NOT_CHECK_PREFIX,
    Observation,
    Reading,
)
from atdd.coach.validators._pr_scope import select_for_current_pr
from atdd.coach.validators._violation import Violation

pytestmark = [pytest.mark.coach, pytest.mark.github_api]


_RULE = bind_rule("coach.pr.merge-blocks-on-pre-smoke-close")
_VALIDATOR_ID = "pr_merge_blocks_pre_smoke_close"

# Phases where an auto-closing PR must NOT merge (mirrors phase_labels.merge_blocked
# in pr.convention.yaml). INIT/PLANNED are included defensively — those phases
# should not have a code PR open against them, and if one exists with a
# Closes #N, the same lifecycle gap applies.
_BLOCKED_PHASES = frozenset({"INIT", "PLANNED", "RED", "GREEN"})

# Strategies that prove the PR will auto-close the linked issue on merge.
# These are the four strategies PRManager.resolve_linked_issue tries; only
# the first two ("api" = closingIssuesReferences, "body" = Closes/Fixes/
# Resolves keyword in body) actually trigger GitHub's auto-close. The
# "manifest" and "title" strategies are weaker inference — they identify a
# linked issue but DO NOT fire auto-close.
_AUTO_CLOSING_STRATEGIES = frozenset({"api", "body"})

# The label every issue this rule governs carries. Used only to decide whether a
# MISSING atdd:<PHASE> label is an unreadable phase (an ATDD issue that must have
# one) or no obligation at all (a plain GitHub issue this lifecycle never claimed).
# Without the distinction, every PR closing an ordinary bug report would refuse.
_ATDD_ISSUE_LABEL = "atdd-issue"


REPO_ROOT = find_repo_root()


def evaluate_pr_merge_violations(
    resolutions: Sequence[dict],
) -> List[Violation]:
    """Pure evaluator: emit one Violation per PR resolution whose phase is blocked.

    Args:
        resolutions: Sequence of dicts shaped like the return value of
            ``PRManager.resolve_linked_issue`` but with one added key:
            ``pr_number`` (since ``resolve_linked_issue`` doesn't echo it).

    Pure function — no GitHub access — so helper tests can drive it from
    synthetic fixtures without hitting the network.
    """
    violations: List[Violation] = []
    for entry in resolutions:
        if entry is None:
            continue
        pr_number = entry.get("pr_number")
        issue_number = entry.get("issue_number")
        phase = entry.get("phase_label")
        strategy = entry.get("strategy")
        if not pr_number or not issue_number or not phase:
            continue
        if strategy not in _AUTO_CLOSING_STRATEGIES:
            # Weak linkage (manifest/title) does not fire GitHub auto-close,
            # so the lifecycle gap is not realized on merge.
            continue
        if phase not in _BLOCKED_PHASES:
            continue

        detail = (
            f"PR #{pr_number} → issue #{issue_number} (phase=atdd:{phase}) "
            f"auto-closes via strategy={strategy!r} but the issue has not "
            f"transitioned through SMOKE+REFACTOR. Merging this PR would "
            f"fire GitHub's auto-close before the lifecycle reaches SMOKE. "
            f"Drive the issue forward: "
            f"`atdd coach transition {issue_number} SMOKE` then "
            f"`atdd coach transition {issue_number} REFACTOR`, or remove the "
            f"Closes/Fixes/Resolves keyword from the PR body if this PR is "
            f"a partial step. See issue #681."
        )
        violations.append(
            Violation(
                rule_id=_RULE.rule_id,
                severity=_RULE.severity,
                location=f"PR#{pr_number}:0",
                detail=detail,
                fix_hint_ref=getattr(_RULE, "fix_hint_ref", None),
            )
        )
        logging.getLogger(__name__).error(
            "%s: PR #%d auto-closes issue #%d at atdd:%s (strategy=%s)",
            _RULE.rule_id, pr_number, issue_number, phase, strategy,
            extra={
                "pr": pr_number,
                "issue": issue_number,
                "phase": phase,
                "strategy": strategy,
                "rule_id": _RULE.rule_id,
            },
        )
    return violations


def _issue_is_atdd_governed(issue_data: Any) -> bool:
    """True when the linked issue carries the ``atdd-issue`` label.

    Only such an issue is *owed* an ``atdd:<PHASE>`` label, so only for such an
    issue is a missing phase an unreadable observation rather than a plain
    "this rule has no business here".
    """
    labels = (issue_data or {}).get("labels", []) or []
    for lbl in labels:
        name = lbl.get("name") if isinstance(lbl, dict) else lbl
        if str(name) == _ATDD_ISSUE_LABEL:
            return True
    return False


def _declared_auto_close_target(mgr: Any, pr: dict) -> Optional[int]:
    """The issue number this PR's merge WILL auto-close, per GitHub's own rules.

    Asked through ``PRManager``'s two auto-closing strategies rather than a
    second regex here, so this can never disagree with the resolver about what
    "declares an auto-close" means. Both read the ``fetch_open_prs`` row
    directly — it already carries ``closingIssuesReferences`` and ``body`` — so
    establishing that a link was DECLARED costs no extra API call and, crucially,
    survives the failure of the per-PR fetch that would hide it.
    """
    return mgr._resolve_via_api(pr) or mgr._resolve_via_body(pr)


def _observed(pr_number: Any, resolution: dict) -> Reading:
    """Hand the resolution on for the rule to judge, with the PR number attached.

    ``PRManager.resolve_linked_issue`` does not echo the PR number; the evaluator
    needs it to build a ``Violation`` location without re-querying.
    """
    entry = dict(resolution)
    entry["pr_number"] = pr_number
    return Reading.observed(entry, subject=pr_number)


def _read_declared_auto_close(
    pr_number: Any, declared: int, resolution: Optional[dict],
) -> Reading:
    """Classify a PR that GitHub WILL auto-close something for on merge.

    Everything here is an unreadable observation unless the thing that came back
    is demonstrably the declared target, read through a strategy that actually
    fires auto-close. Anything looser lets the resolver's weaker fallbacks —
    branch-slug and title matching, which do NOT fire auto-close — stand in for a
    reference whose own read failed, which is the substitution #1747 is about.
    """
    if resolution is None:
        return Reading.unreadable(
            f"PR #{pr_number} will auto-close issue #{declared} on merge, but the "
            f"link did not resolve — the PR or the issue could not be read from "
            f"GitHub. Re-run once the API is reachable "
            f"(run `gh pr view {pr_number}` and `gh issue view {declared}` to see "
            f"which half is failing); until it resolves, this gate cannot tell "
            f"whether the merge would close a pre-SMOKE issue. See issue #681.",
            subject=pr_number,
        )

    issue_number = resolution.get("issue_number")
    if (
        issue_number != declared
        or resolution.get("strategy") not in _AUTO_CLOSING_STRATEGIES
    ):
        return Reading.unreadable(
            f"PR #{pr_number} will auto-close issue #{declared} on merge, but the "
            f"resolver answered with issue #{issue_number} via "
            f"strategy={resolution.get('strategy')!r} — a weaker inference that "
            f"does not fire auto-close. #{declared} itself was never read, so the "
            f"phase this merge would close at is unobserved. "
            f"(run `gh issue view {declared} --json labels` to see whether it is "
            f"reachable). See issue #681.",
            subject=pr_number,
        )

    if resolution.get("phase_label"):
        return _observed(pr_number, resolution)

    # The issue read fine but carries no atdd:<PHASE>. For an ATDD-governed issue
    # that is a phase we could not observe; for any other issue the lifecycle
    # never claimed it, and refusing there would block every PR that closes an
    # ordinary bug report.
    if _issue_is_atdd_governed(resolution.get("issue_data")):
        return Reading.unreadable(
            f"PR #{pr_number} will auto-close issue #{issue_number} on merge, and "
            f"#{issue_number} is an ATDD issue, but it carries no atdd:<PHASE> "
            f"label — so the phase this gate compares against could not be "
            f"observed. Restore the phase label "
            f"(run `gh issue view {issue_number} --json labels` to inspect, then "
            f"`atdd coach reconcile` to resync it from the State Store). "
            f"See issue #681.",
            subject=pr_number,
        )
    return Reading.no_obligation(
        f"PR #{pr_number} links issue #{issue_number}, which carries no "
        f"atdd:<PHASE> label and is not an ATDD-governed issue",
        subject=pr_number,
    )


def read_pr_issue_link(mgr: Any, pr: dict) -> Reading:
    """Did this PR's auto-closing link resolve — and if not, which kind of not?

    The #1747 fix in one function. ``resolve_linked_issue`` collapses "no link
    declared" and "link declared but unreadable" into one ``None``; this splits
    them back apart by asking the PR row what it DECLARES — through PRManager's
    own two auto-closing strategies, off data ``fetch_open_prs`` already returned
    — before deciding what a failed resolution meant.

    Returns a :class:`Reading` that is one of:

    * ``observed`` — payload is the resolution dict with ``pr_number`` added,
      ready for :func:`evaluate_pr_merge_violations` to apply the rule to.
    * ``unreadable`` — the PR declares an auto-closing reference whose issue or
      phase could not be read. ``COULD_NOT_CHECK``; refuses.
    * ``no_obligation`` — merging cannot fire the auto-close this rule exists to
      prevent. ``NOT_APPLICABLE``; proceeds.
    """
    pr_number = pr.get("number")
    declared = _declared_auto_close_target(mgr, pr)
    resolution = mgr.resolve_linked_issue(pr_number)

    if declared is not None:
        return _read_declared_auto_close(pr_number, declared, resolution)

    if resolution is None:
        return Reading.no_obligation(
            f"PR #{pr_number} declares no Closes/Fixes/Resolves reference and no "
            f"closingIssuesReferences entry, so merging it cannot fire GitHub's "
            f"auto-close",
            subject=pr_number,
        )
    # A weak (manifest/title) link with no declared auto-close. Nothing was
    # missed — hand it to the evaluator, which skips weak strategies for the same
    # reason: they identify an issue but do not close it.
    return _observed(pr_number, resolution)


def evaluate_link_readings(readings: Sequence[Reading]) -> List[Violation]:
    """Turn unreadable links into refusals, and observed ones into rule verdicts.

    Both arrive as ordinary ``Violation`` records because the disposition gate
    speaks nothing else; the ``COULD_NOT_CHECK`` ones are marked in their detail
    text so an operator can tell "I could not look at your PR" from "your PR is
    unmergeable" without reading this source. Readings that carry no obligation
    contribute nothing, which is what ``NOT_APPLICABLE`` means.
    """
    violations: List[Violation] = []
    observed: List[dict] = []
    log = logging.getLogger(__name__)

    for reading in readings:
        if reading.observation is Observation.OBSERVED:
            observed.append(reading.payload)
            continue
        if not reading.blocks:
            log.info(
                "%s: %s (verdict=%s)",
                _RULE.rule_id, reading.reason, reading.verdict.value,
                extra={"rule_id": _RULE.rule_id, "verdict": reading.verdict.value},
            )
            continue
        # The location must carry ``PR#<n>:`` or _pr_scope cannot scope the
        # refusal to the PR under validation — which is what keeps one PR's
        # unreadable link from reddening every other contributor's CI (E070).
        violations.append(
            Violation(
                rule_id=_RULE.rule_id,
                severity=_RULE.severity,
                location=f"PR#{reading.subject}:0",
                detail=f"{COULD_NOT_CHECK_PREFIX} {reading.reason}",
                fix_hint_ref=getattr(_RULE, "fix_hint_ref", None),
            )
        )
        log.error(
            "%s: could not observe PR #%s's link; refusing rather than passing",
            _RULE.rule_id, reading.subject,
            extra={
                "pr": reading.subject,
                "rule_id": _RULE.rule_id,
                "verdict": reading.verdict.value,
            },
        )

    return violations + evaluate_pr_merge_violations(observed)


def scan_open_prs_for_pre_smoke_close(
    repo_root: Optional[Path] = None,
) -> List[Violation]:
    """End-to-end scanner: fetch open PRs, read their links, emit Violations."""
    root = repo_root or REPO_ROOT
    mgr = PRManager(target_dir=root)
    open_prs = mgr.fetch_open_prs()

    readings = [
        read_pr_issue_link(mgr, pr) for pr in open_prs if pr.get("number")
    ]
    return evaluate_link_readings(readings)


# ---------------------------------------------------------------------------
# PR-under-test scoping (WMBT E056)
# ---------------------------------------------------------------------------


_PULL_REF = re.compile(r"^refs/pull/(\d+)/")


def _branch_pr_number(repo_root: Optional[Path] = None) -> Optional[int]:
    """Resolve the current git branch's open PR via PRManager (no CI env needed)."""
    try:
        mgr = PRManager(target_dir=repo_root or REPO_ROOT)
        branch = mgr._detect_branch()
        if not branch:
            return None
        return mgr.pr_number_for_branch(branch)
    except Exception as exc:  # network/parse failure -> treat as unresolvable
        logging.getLogger(__name__).warning(
            "could not resolve current branch PR; gate degrades to advisory-only",
            extra={"error": str(exc)},
        )
        return None


def _current_pr_number(repo_root: Optional[Path] = None) -> Optional[int]:
    """Resolve the PR currently under test from CI context.

    Order: ``ATDD_PR_NUMBER`` / ``PR_NUMBER`` env → ``GITHUB_REF`` of the form
    ``refs/pull/<N>/merge`` (GitHub Actions pull_request event) → the current
    branch's open PR via ``PRManager``.

    Returns None when none resolves — a local repo-health run, or a branch whose
    PR does not exist yet (the 12:58:31Z ``push`` leg of #1747's flip). That is
    ``NOT_APPLICABLE``, NOT ``COULD_NOT_CHECK``: a branch with no PR cannot merge
    anything, so this gate is owed nothing by it and must not block it. The brief
    says so directly — "the link could not be READ" is not "the issue has no PR".
    What the run then reports is not a bare PASS either; see
    :func:`test_no_open_pr_closes_an_issue_in_pre_smoke_phase`, which logs which
    of the two it is.
    """
    for var in ("ATDD_PR_NUMBER", "PR_NUMBER"):
        val = os.environ.get(var, "").strip()
        if val.isdigit():
            return int(val)

    m = _PULL_REF.match(os.environ.get("GITHUB_REF", "").strip())
    if m:
        return int(m.group(1))

    return _branch_pr_number(repo_root)


def select_blocking_violations(
    violations: Sequence[Violation], current_pr: Optional[int]
) -> List[Violation]:
    """Select the violations that should FAIL the strict gate on this CI run.

    With a resolved ``current_pr``, only that PR's violation blocks (so an innocent
    PR is not failed by other PRs' offenses, while an offending PR is still blocked
    on its own CI).

    With NO current PR the gate is advisory-only: nothing blocks. E056 shipped the
    opposite — unresolvable meant block every offender, called "repo-wide
    back-compat" — but that fallback IS the cross-PR coupling E056 set out to
    remove, and the branch-leg bug (#1478) made it the common path rather than the
    rare one. An offender is blocked on the run that CAN name it as its own PR.

    Every offender is still produced + logged by the scan; this only narrows what
    FAILS the disposition gate.
    """
    return select_for_current_pr(violations, current_pr)


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


def test_no_open_pr_closes_an_issue_in_pre_smoke_phase():
    """
    SPEC: ``pr.convention.yaml::rules[coach.pr.merge-blocks-on-pre-smoke-close]``.

    Given:  Every open PR returned by ``gh pr list --state open`` that has
            an auto-closing reference (Closes/Fixes/Resolves keyword OR a
            GraphQL ``closingIssuesReferences`` entry) to an ATDD issue.
    When:   Comparing the linked issue's atdd:<PHASE> label against the
            merge-eligibility set {SMOKE, REFACTOR, COMPLETE}.
    Then:   No open PR auto-closes an issue still at atdd:RED or atdd:GREEN
            (or INIT/PLANNED). PRs that violate this gap surface as
            structured ``Violation`` records the disposition gate fails on.
            And:    a PR whose declared auto-close link could NOT be read
            surfaces as a ``COULD_NOT_CHECK`` record, which the same strict
            gate fails on — the gate never reports green for a PR it did not
            observe (#1747). Strict disposition — bypass forbidden.
    """
    # Scan + log every offender (repo-health visibility), then scope the strict
    # FAILURE to the PR under test: an innocent PR is not failed by another PR's
    # offense, while every offender is still blocked on its own CI (E056).
    all_violations = scan_open_prs_for_pre_smoke_close(REPO_ROOT)
    current_pr = _current_pr_number(REPO_ROOT)
    if current_pr is None:
        # Say which kind of green this is. A branch with no PR is owed nothing by
        # a merge gate, so it proceeds — but it proceeds as NOT_APPLICABLE, not as
        # a PASS. The unlabelled green on head sha 54bdad8af at 12:58:31Z, two
        # seconds before PR #1757 existed, is what made #1747 invisible for six
        # hours of deliberate scrutiny.
        logging.getLogger(__name__).info(
            "%s: %s — no PR under validation on this run, so this gate has "
            "nothing to observe (it did NOT verify any PR)",
            _RULE.rule_id, GateVerdict.NOT_APPLICABLE.value,
            extra={
                "rule_id": _RULE.rule_id,
                "verdict": GateVerdict.NOT_APPLICABLE.value,
                "offenders_seen": len(all_violations),
            },
        )
    blocking = select_blocking_violations(all_violations, current_pr)
    assert_disposition_satisfied(
        validator_id=_VALIDATOR_ID,
        violations=blocking,
    )
