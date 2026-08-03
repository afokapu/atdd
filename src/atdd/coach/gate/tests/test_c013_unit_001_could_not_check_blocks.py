# URN: test:govern-lifecycle:enforcing-phase-transition-gate:C013-UNIT-001-could-not-check-refuses-the-transition
# Acceptance: acc:govern-lifecycle:C013-UNIT-001-could-not-check-refuses-the-transition
# WMBT: wmbt:govern-lifecycle:C013
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C013-UNIT-001 — a check that could not observe refuses the transition.

``GateCheckResult`` carried a ``passed: bool``, so a check that reached a branch
where it could not perform its observation had only ``True`` available if it did
not want to block. "I could not look" was spelled exactly like "I looked and it
was fine", and ``evaluate_gate`` advanced on the second reading of the first fact.

This file holds the new answer: ``COULD_NOT_CHECK`` blocks, exactly as ``FAIL``
blocks. It also holds the two verdicts that already decided the gate to their
existing behaviour, because a third state is only worth adding if it does not
disturb C007's AND-semantics on the way in.

RED state: ``atdd.coach.gate.decision`` declares no ``GateVerdict``.
"""
from __future__ import annotations

import pytest

from atdd.coach.gate.decision import GateCheckResult, GateVerdict, evaluate_gate

pytestmark = [pytest.mark.platform]

_RULE = "repo.govern-lifecycle.c013"


def _blind(gate_id: str = "GT-BLIND") -> GateCheckResult:
    return GateCheckResult.could_not_check(gate_id, _RULE, "the observation could not be performed")


def _green(gate_id: str = "GT-OK") -> GateCheckResult:
    return GateCheckResult.passing(gate_id, _RULE, "observed and satisfied")


def _red(gate_id: str = "GT-BAD") -> GateCheckResult:
    return GateCheckResult.failing(gate_id, _RULE, "observed and violated")


def test_a_check_that_could_not_observe_blocks_the_transition():
    """The whole point: an unmade observation is not a clean one."""
    outcome = evaluate_gate([_blind()])

    assert outcome.proceed is False, (
        "a check that could not perform its observation let the transition through — "
        "this is the defect the verdict exists to remove"
    )


def test_could_not_check_blocks_even_when_every_other_check_passed():
    """One unmade observation is sufficient to refuse.

    The dangerous shape is not an all-blind run — it is a run where the blind
    check is outnumbered by real passes and its verdict gets absorbed into a
    green aggregate.
    """
    outcome = evaluate_gate([_green("GT-A"), _blind("GT-B"), _green("GT-C")])

    assert outcome.proceed is False, (
        "a COULD_NOT_CHECK result was outvoted by passing checks; the gate "
        "aggregates with AND-semantics, not by majority"
    )
    assert len(outcome.results) == 3, "no verdict may be dropped from the outcome"


def test_all_passing_checks_still_proceed():
    """No regression to C007-UNIT-002: the ordinary green path is untouched."""
    outcome = evaluate_gate([_green("GT-A"), _green("GT-B")])

    assert outcome.proceed is True
    assert outcome.failures == ()


def test_a_failing_check_still_blocks_and_is_still_enumerated():
    """No regression to C007-UNIT-001: FAIL keeps deciding the gate as it did."""
    outcome = evaluate_gate([_green("GT-A"), _red("GT-B"), _green("GT-C")])

    assert outcome.proceed is False
    assert len(outcome.failures) == 1
    assert outcome.failures[0].gate_id == "GT-B"


def test_the_blocking_verdicts_are_exactly_fail_and_could_not_check():
    """Stated on the verdict itself, so the gate and a reader cannot disagree."""
    assert GateVerdict.FAIL.blocks is True
    assert GateVerdict.COULD_NOT_CHECK.blocks is True
    assert GateVerdict.PASS.blocks is False
