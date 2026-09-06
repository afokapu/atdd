# URN: test:author-atdd-substrate:pr-phase-alignment:PRGATE-UNIT-002-scopes-to-pr-under-validation
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""PRGATE-UNIT-002 — the early-phase gate scopes like its siblings (#1478/E070).

    An innocent PR is not failed by another PR's lifecycle skip.

COACH-PRGATE-0002 is strict and scans every open PR, so without `_pr_scope` it
would red every contributor's CI for a state their branch neither created nor
can fix — the cross-PR coupling #1478 named. Its two sibling PR gates already
route through the shared selector; this one did not, which is the only reason
strict looked like a fleet stoppage.

Its violation locations are `PR#<n>:0`, the same shape as the pre-SMOKE gate,
so the shared prefix selector applies unchanged.
"""
from __future__ import annotations

from atdd.coach.validators._pr_scope import select_for_current_pr
from atdd.coach.validators._violation import Violation
from atdd.coach.validators.test_pr_phase_alignment import RULE_ID_PRGATE_EARLY


def _violation(pr_number: int) -> Violation:
    return Violation(
        rule_id=RULE_ID_PRGATE_EARLY,
        severity=4,
        location=f"PR#{pr_number}:0",
        detail=f"PR #{pr_number} ships code while its issue is at INIT",
    )


def test_innocent_pr_not_blocked_by_a_sibling_offender() -> None:
    offenders = [_violation(1763), _violation(1764)]
    assert select_for_current_pr(offenders, current_pr=1793) == []


def test_offender_is_blocked_on_its_own_run() -> None:
    offenders = [_violation(1763), _violation(1764)]
    blocking = select_for_current_pr(offenders, current_pr=1764)
    assert [v.location for v in blocking] == ["PR#1764:0"]


def test_unresolvable_pr_blocks_nothing() -> None:
    """A local run or a branch before its PR exists cannot name itself."""
    assert select_for_current_pr([_violation(1763)], current_pr=None) == []
