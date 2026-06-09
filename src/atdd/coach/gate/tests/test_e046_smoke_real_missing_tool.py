# URN: test:govern-lifecycle:enforcing-phase-transition-gate:E046-SMOKE-001-real-missing-tool-fails-closed
# Acceptance: acc:govern-lifecycle:E046-SMOKE-001-real-missing-tool-fails-closed
# WMBT: wmbt:govern-lifecycle:E046
# Phase: SMOKE
# Layer: integration
# Smoke: true
# Assertion: behavioral
# Purpose: prove fail-closed against the REAL OS raising FileNotFoundError for a missing binary
"""E046-SMOKE-001 — fail-closed against a REAL missing tool.

No fakes: a real CommandGateCheck names a binary that genuinely does not exist
on the host PATH. The real OS raises FileNotFoundError when subprocess tries to
exec it, and the gate converts that into a FAIL — so the real
evaluate_transition_gate blocks. This is the fail-closed guarantee verified
against real infrastructure, not a stubbed exception.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.gate.command_check import CommandGateCheck
from atdd.coach.gate.decision import GateContext, evaluate_transition_gate
from atdd.coach.gate.registry import GateRegistry

pytestmark = [pytest.mark.platform]


def test_real_missing_tool_fails_closed(tmp_path: Path):
    check = CommandGateCheck(
        gate_id="GT-SMOKE-MISSING",
        rule_id="repo.govern-lifecycle.E046-smoke-missing",
        command=["atdd-definitely-no-such-binary-9f3c2", "gate"],
        timeout=15.0,
    )
    registry = GateRegistry()
    registry.register("PLANNED", "RED", check)
    config = {"gate": {"transitions": {"PLANNED->RED": True}}}
    ctx = GateContext(
        issue_number=1020, from_phase="PLANNED", to_phase="RED", worktree=tmp_path
    )

    outcome = evaluate_transition_gate(registry, config, ctx)

    assert outcome.proceed is False, "a real missing tool must be fail-closed"
    assert any(f.gate_id == "GT-SMOKE-MISSING" for f in outcome.failures)
