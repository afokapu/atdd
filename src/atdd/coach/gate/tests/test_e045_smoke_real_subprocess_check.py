# URN: test:govern-lifecycle:enforcing-phase-transition-gate:E045-SMOKE-001-real-subprocess-check-blocks-through-live-registry
# Acceptance: acc:govern-lifecycle:E045-SMOKE-001-real-subprocess-check-blocks-through-live-registry
# WMBT: wmbt:govern-lifecycle:E045
# Phase: SMOKE
# Layer: integration
# Smoke: true
# Assertion: behavioral
# Purpose: exercise the gate against a REAL OS subprocess through the live registry + decision path
"""E045-SMOKE-001 — the gate blocks/proceeds against a REAL subprocess.

No fakes, no mocks: a real CommandGateCheck shells out to a real Python
subprocess that genuinely exits 1 (fail) or 0 (pass), registered into a real
GateRegistry and decided by the real evaluate_transition_gate. This is the
production wiring (CommandGateCheck -> registry -> decision -> OS process) the
hermetic unit/integration tests stub at the check boundary.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from atdd.coach.gate.command_check import CommandGateCheck
from atdd.coach.gate.decision import GateContext, evaluate_transition_gate
from atdd.coach.gate.registry import GateRegistry

pytestmark = [pytest.mark.platform]

_GATED_CONFIG = {"gate": {"transitions": {"PLANNED->RED": True}}}


def _ctx(tmp_path: Path) -> GateContext:
    return GateContext(
        issue_number=1020, from_phase="PLANNED", to_phase="RED", worktree=tmp_path
    )


def test_real_failing_subprocess_blocks(tmp_path: Path):
    """A real command that genuinely exits non-zero blocks the transition."""
    check = CommandGateCheck(
        gate_id="GT-SMOKE-FAIL",
        rule_id="repo.govern-lifecycle.E045-smoke-fail",
        command=[sys.executable, "-c", "import sys; sys.exit(1)"],
        timeout=15.0,
    )
    registry = GateRegistry()
    registry.register("PLANNED", "RED", check)

    outcome = evaluate_transition_gate(registry, _GATED_CONFIG, _ctx(tmp_path))

    assert outcome.proceed is False
    assert any(f.gate_id == "GT-SMOKE-FAIL" for f in outcome.failures)


def test_real_passing_subprocess_proceeds(tmp_path: Path):
    """A real command that genuinely exits 0 lets the transition proceed."""
    check = CommandGateCheck(
        gate_id="GT-SMOKE-PASS",
        rule_id="repo.govern-lifecycle.E045-smoke-pass",
        command=[sys.executable, "-c", "import sys; sys.exit(0)"],
        timeout=15.0,
    )
    registry = GateRegistry()
    registry.register("PLANNED", "RED", check)

    outcome = evaluate_transition_gate(registry, _GATED_CONFIG, _ctx(tmp_path))

    assert outcome.proceed is True
