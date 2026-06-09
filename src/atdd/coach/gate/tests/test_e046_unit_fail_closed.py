# URN: test:govern-lifecycle:enforcing-phase-transition-gate:E046-UNIT-001-raising-check-becomes-failing-result
# Acceptance: acc:govern-lifecycle:E046-UNIT-001-raising-check-becomes-failing-result
# Acceptance: acc:govern-lifecycle:E046-UNIT-002-timeout-or-missing-tool-is-fail-closed
# WMBT: wmbt:govern-lifecycle:E046
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""E046 — the gate is fail-closed.

A check that errors or times out must become a FAILING result, never a silent
pass. run_checks() catches any exception from a check's run() and converts it to
a failing GateCheckResult; a CommandGateCheck whose command times out / is
missing therefore makes evaluate_transition_gate return proceed=False.

RED state: there is no atdd.coach.gate module, so run_checks / CommandGateCheck /
evaluate_transition_gate do not exist.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from atdd.coach.gate.decision import (
    GateCheckResult,
    GateContext,
    evaluate_transition_gate,
    run_checks,
)
from atdd.coach.gate.registry import GateRegistry
from atdd.coach.gate.command_check import CommandGateCheck

pytestmark = [pytest.mark.platform]


@dataclass
class _RaisingCheck:
    gate_id: str = "GT-RAISE"
    rule_id: str = "repo.govern-lifecycle.E046-raise"

    def run(self, ctx) -> GateCheckResult:
        raise RuntimeError("check blew up")


def _ctx(tmp_path: Path) -> GateContext:
    return GateContext(
        issue_number=1020,
        from_phase="PLANNED",
        to_phase="RED",
        worktree=tmp_path,
    )


def test_raising_check_becomes_failing_result(tmp_path: Path):
    """E046-UNIT-001: run_checks converts a raising check into a failing result."""
    results = run_checks([_RaisingCheck()], _ctx(tmp_path))

    assert len(results) == 1
    r = results[0]
    assert r.passed is False, "a raising check must be fail-closed, not dropped or passed"
    assert r.gate_id == "GT-RAISE"
    assert r.rule_id == "repo.govern-lifecycle.E046-raise"
    assert r.message, "the failing result must carry a non-empty message"


def test_timeout_or_missing_tool_is_fail_closed(tmp_path: Path):
    """E046-UNIT-002: a CommandGateCheck that cannot complete blocks the transition.

    A command that does not exist (FileNotFoundError) or times out must be a
    FAIL — proven by evaluate_transition_gate returning proceed=False with the
    failure attributed to the CommandGateCheck.
    """
    check = CommandGateCheck(
        gate_id="GT-CMD",
        rule_id="repo.govern-lifecycle.E046-cmd",
        command=["atdd-no-such-binary-xyz", "gate"],
        timeout=1.0,
    )
    registry = GateRegistry()
    registry.register("PLANNED", "RED", check)

    # Empty config -> PLANNED->RED gated by default.
    outcome = evaluate_transition_gate(registry, {}, _ctx(tmp_path))

    assert outcome.proceed is False, "missing tool must be fail-closed (FAIL), not a silent pass"
    assert any(f.gate_id == "GT-CMD" for f in outcome.failures), (
        "the failure must be attributed to the CommandGateCheck"
    )
