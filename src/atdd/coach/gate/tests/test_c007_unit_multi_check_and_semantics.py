# URN: test:govern-lifecycle:enforcing-phase-transition-gate:C007-UNIT-001-any-failing-check-blocks
# Acceptance: acc:govern-lifecycle:C007-UNIT-001-any-failing-check-blocks
# Acceptance: acc:govern-lifecycle:C007-UNIT-002-all-passing-checks-proceed
# WMBT: wmbt:govern-lifecycle:C007
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C007 — evaluate_gate aggregates ALL registered check results with AND-semantics.

The registry holds a LIST of checks per transition (so #958, #1017 and existing
validate gates can all register onto one (from -> to) transition). The gate
proceeds only when EVERY check passed; if ANY check fails the transition is
blocked and every failing check is enumerated. No short-circuit, no majority.

RED state: there is no atdd.coach.gate.decision module / evaluate_gate.
"""
from __future__ import annotations

import pytest

from atdd.coach.gate.decision import GateCheckResult, evaluate_gate

pytestmark = [pytest.mark.platform]


def _result(gate_id: str, passed: bool) -> GateCheckResult:
    return GateCheckResult(
        gate_id=gate_id,
        rule_id=f"repo.govern-lifecycle.{gate_id}",
        passed=passed,
        message="ok" if passed else "failed",
    )


def test_any_failing_check_blocks():
    """C007-UNIT-001: pass, fail, pass -> proceed=False, the one failure enumerated."""
    results = [
        _result("GT-A", True),
        _result("GT-B", False),
        _result("GT-C", True),
    ]

    outcome = evaluate_gate(results)

    assert outcome.proceed is False, "any failing check must block the transition"
    assert len(outcome.failures) == 1
    assert outcome.failures[0].gate_id == "GT-B"
    assert len(outcome.results) == 3, "all results must be preserved on the outcome"


def test_all_passing_checks_proceed():
    """C007-UNIT-002: all-pass -> proceed=True, no failures."""
    outcome = evaluate_gate([_result("GT-A", True), _result("GT-B", True)])

    assert outcome.proceed is True
    assert outcome.failures == ()
