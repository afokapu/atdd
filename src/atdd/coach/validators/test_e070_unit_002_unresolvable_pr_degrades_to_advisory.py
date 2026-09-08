# URN: test:govern-lifecycle:enforce-smoke-refactor-phase-substrate:E070-UNIT-002-unresolvable-pr-degrades-to-advisory
# Acceptance: acc:govern-lifecycle:E070-UNIT-002-unresolvable-pr-degrades-to-advisory
# WMBT: wmbt:govern-lifecycle:E070
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""E070-UNIT-002 — an unresolvable PR under validation blocks nothing.

E056 shipped ``current_pr is None -> block every offender`` as "repo-wide back-compat".
That fallback IS the cross-PR coupling E056 set out to remove: any run that cannot name
its own PR (a push-event CI run whose branch leg failed, a branch with no PR open yet, a
local repo-health run) is failed by whichever stranger's PR happens to be offending.

Unresolvable now means advisory-only: the offenders are still produced and logged, but
nothing blocks. An offender is blocked on the run that CAN name it as its own PR.
"""
from __future__ import annotations

from atdd.coach.validators import test_pr_closes_keyword_discipline as closes_mod
from atdd.coach.validators import test_pr_merge_blocks_pre_smoke_close as presmoke_mod
from atdd.coach.validators._violation import Violation


def _presmoke_violation(pr_number: int) -> Violation:
    return Violation(
        rule_id="coach.pr.merge-blocks-on-pre-smoke-close",
        severity=4,
        location=f"PR#{pr_number}:0",
        detail=f"PR #{pr_number} offends",
    )


def _closes_violation(pr_number: int) -> Violation:
    return Violation(
        rule_id="coach.pr.closes-keyword-discipline",
        severity=4,
        location=f"PR#{pr_number}:body",
        detail=f"PR #{pr_number} offends",
    )


def test_pre_smoke_gate_blocks_nothing_when_no_pr_resolves() -> None:
    violations = [_presmoke_violation(1461), _presmoke_violation(1456)]
    assert presmoke_mod.select_blocking_violations(violations, current_pr=None) == []


def test_closes_keyword_gate_blocks_nothing_when_no_pr_resolves() -> None:
    violations = [_closes_violation(1461), _closes_violation(1456)]
    assert closes_mod.select_blocking_violations(violations, current_pr=None) == []


def test_offenders_are_still_produced_for_visibility() -> None:
    """Advisory-only narrows what FAILS; it must not narrow what is SEEN."""
    resolutions = [
        {"pr_number": 1461, "issue_number": 1193, "phase_label": "PLANNED", "strategy": "api"},
    ]
    all_violations = presmoke_mod.evaluate_pr_merge_violations(resolutions)
    assert [v.location for v in all_violations] == ["PR#1461:0"]
    assert presmoke_mod.select_blocking_violations(all_violations, current_pr=None) == []
