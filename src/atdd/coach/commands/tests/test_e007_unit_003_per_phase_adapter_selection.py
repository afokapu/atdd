# URN: test:spawn-agents:per-phase-fresh-agent-respawn:E007-UNIT-003-per-phase-adapter-selection-honored
# Acceptance: acc:spawn-agents:E007-UNIT-003-per-phase-adapter-selection-honored
# WMBT: wmbt:spawn-agents:E007
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""E007-UNIT-003 — the relaunch command for a phase is built from the
adapter/model selected for THAT phase, not inherited from the prior phase.

RED: the spawn handler resolves the LLM per *persona* (``_resolve_llm`` reads
``ctx.persona_llm`` / ``ctx.llm``). The tester persona drives both RED and
SMOKE, so today both phases relaunch with the same adapter — a per-phase
selection (RED on one model, SMOKE on another) is ignored. This test pins
per-phase adapter selection: two same-persona phases with distinct selections
must relaunch with distinct commands.
"""
from __future__ import annotations

import pytest

from atdd.coach.commands.tests._e007_respawn_harness import (
    FakeRespawnMx,
    patch_spawn_env,
)
from atdd.coach.handlers.state_machine import (
    CoachContext,
    HandlerResult,
    Phase,
    Transition,
)

pytestmark = [pytest.mark.platform]


def test_per_phase_adapter_selection_honored(tmp_path, monkeypatch):
    """RED (tester) and SMOKE (tester) carry distinct per-phase adapter
    selections — the relaunch commands must differ accordingly."""
    from atdd.coach.commands import spawn as cmd_spawn_mod

    # A second adapter so a phase can select something other than claude-code.
    monkeypatch.setitem(
        cmd_spawn_mod.ADAPTER_REGISTRY,
        "fake-fast",
        lambda prompt_path: "fake-fast-cli --launch",
    )

    fake_mx = FakeRespawnMx()
    spawn_handler = patch_spawn_env(tmp_path, monkeypatch, fake_mx)

    ctx = CoachContext(issue_number=746, multiplexer_mode="pane")
    # Per-phase selection: RED runs claude-code, SMOKE runs the fast adapter.
    # Both phases are driven by the SAME persona (tester) — a per-persona
    # resolution cannot tell them apart.
    ctx.phase_llm = {"red": "claude-code", "smoke": "fake-fast"}

    transitions = [
        Transition(src=Phase.INIT, dst=Phase.PLANNED),
        Transition(src=Phase.PLANNED, dst=Phase.RED),
        Transition(src=Phase.RED, dst=Phase.GREEN),
        Transition(src=Phase.GREEN, dst=Phase.SMOKE),
    ]
    for t in transitions:
        assert spawn_handler.handle(ctx, t) == HandlerResult.HANDLED, (
            f"transition {t.src.value}->{t.dst.value} did not spawn"
        )

    launches = fake_mx.spawn_or_respawn_calls()
    assert len(launches) == 4, (
        f"expected one launch per transition, got {len(launches)}: {launches}"
    )
    red_command = launches[1]["command"] or ""
    smoke_command = launches[3]["command"] or ""

    assert red_command != smoke_command, (
        "RED and SMOKE relaunched with the SAME command despite distinct "
        f"per-phase adapter selections: {red_command!r}"
    )
    assert "fake-fast" in smoke_command, (
        f"the SMOKE phase did not relaunch with its selected adapter "
        f"(fake-fast): {smoke_command!r}"
    )
    assert "claude" in red_command, (
        f"the RED phase did not relaunch with its selected adapter "
        f"(claude-code): {red_command!r}"
    )
