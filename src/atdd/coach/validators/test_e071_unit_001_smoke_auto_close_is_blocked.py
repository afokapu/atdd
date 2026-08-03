# URN: test:govern-lifecycle:enforce-smoke-refactor-phase-substrate:E071-UNIT-001-smoke-auto-close-is-blocked
# Acceptance: acc:govern-lifecycle:E071-UNIT-001-smoke-auto-close-is-blocked
# WMBT: wmbt:govern-lifecycle:E071
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""E071-UNIT-001 — an auto-close that would fire at atdd:SMOKE is blocked.

The rule's own description says a merge may auto-close only an issue at
``atdd:REFACTOR`` or ``atdd:COMPLETE``. Its enforcement named INIT/PLANNED/RED/
GREEN, so ``atdd:SMOKE`` — the one phase between the two statements — passed.

That is not hypothetical. On 2026-08-03 PR #1691 auto-closed #1689 and PR #1648
auto-closed #1635, both while the issue carried ``atdd:SMOKE``; both issues are
CLOSED/COMPLETED with ``atdd:SMOKE`` still on them and REFACTOR never entered.
REFACTOR is the operator sign-off and the terminal hop to COMPLETE
(``phase_machine.convention.yaml``: ``autonomy: operator``, #1611) — the exact
review the 2026-05-13 substrate-asymmetry incident cost the repo, one phase
further along.

The two directions are asserted together on purpose: a gate that blocks SMOKE
but also blocks REFACTOR and COMPLETE is not a fix, it is an outage.
"""
from __future__ import annotations

import pytest

from atdd.coach.validators import test_pr_merge_blocks_pre_smoke_close as mod

_RULE_ID = "coach.pr.merge-blocks-on-pre-smoke-close"


def _resolution(phase: str, strategy: str = "api") -> dict:
    """One ``PRManager.resolve_linked_issue`` result, plus the PR number the scan adds."""
    return {
        "pr_number": 1673,
        "issue_number": 1622,
        "phase_label": phase,
        "strategy": strategy,
    }


def test_an_auto_close_at_smoke_is_blocked() -> None:
    """The defect, stated as an assertion: SMOKE must not carry a live auto-close."""
    violations = mod.evaluate_pr_merge_violations([_resolution("SMOKE")])

    assert len(violations) == 1, (
        "a PR whose Closes/Fixes/Resolves reference targets an issue at atdd:SMOKE "
        "must be blocked — merging it fires GitHub's auto-close with REFACTOR, the "
        f"operator sign-off, never entered. Got {violations!r}"
    )
    assert violations[0].rule_id == _RULE_ID
    assert violations[0].location == "PR#1673:0"


@pytest.mark.parametrize("strategy", ["api", "body"])
def test_both_auto_closing_strategies_are_blocked_at_smoke(strategy: str) -> None:
    """Either proof of a live auto-close is enough — the API field or the body keyword."""
    assert len(mod.evaluate_pr_merge_violations([_resolution("SMOKE", strategy)])) == 1


@pytest.mark.parametrize("phase", ["INIT", "PLANNED", "RED", "GREEN"])
def test_the_2026_05_13_regression_stays_covered(phase: str) -> None:
    """The incident this rule was written for must still be caught."""
    violations = mod.evaluate_pr_merge_violations([_resolution(phase)])
    assert len(violations) == 1, f"atdd:{phase} must still block; got {violations!r}"


@pytest.mark.parametrize("phase", ["REFACTOR", "COMPLETE"])
def test_merge_is_still_allowed_at_refactor_and_complete(phase: str) -> None:
    """A fix that blocks everything is not a fix — these two must still merge."""
    violations = mod.evaluate_pr_merge_violations([_resolution(phase)])
    assert violations == [], (
        f"atdd:{phase} is merge-eligible by the rule's own description; blocking it "
        f"would stop every merge in the repo. Got {violations!r}"
    )


@pytest.mark.parametrize("strategy", ["manifest", "title"])
def test_weak_linkage_at_smoke_is_not_a_violation(strategy: str) -> None:
    """Only a live auto-close realizes the gap; manifest/title inference fires nothing.

    Open PR #1538 links #1524 (at atdd:SMOKE) by title alone — no GitHub auto-close
    fires on merge, so there is nothing for this rule to prevent.
    """
    assert mod.evaluate_pr_merge_violations([_resolution("SMOKE", strategy)]) == []
