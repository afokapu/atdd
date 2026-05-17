# URN: test:spawn-agents:per-phase-fresh-agent-respawn:E005-UNIT-004-phase-qualified-surface-name
# Acceptance: acc:spawn-agents:E005-UNIT-004-phase-qualified-surface-name
# WMBT: wmbt:spawn-agents:E005
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""E005-UNIT-004 — the worker surface is renamed on each transition to a
phase-qualified name encoding the live phase and persona (e.g.
``ATDD746·RED·tester``).

RED: ``compute_issue_surface_name`` produces ``ATDD<N>`` only — "No slug /
persona / phase segment" — so the operator cannot tell which phase/agent is
live. There is no phase-qualified naming helper, and the respawn path keeps the
surface's ``ATDD<N>`` identity unchanged across transitions. This test pins a
phase-qualified naming helper and a per-transition rename.
"""
from __future__ import annotations

import pytest

from atdd.coach.commands.tests._e005_respawn_harness import (
    FakeRespawnMx,
    patch_spawn_env,
)
from atdd.coach.handlers.state_machine import (
    CoachContext,
    HandlerResult,
    Phase,
    Transition,
)
from atdd.coach.utils import session_naming

pytestmark = [pytest.mark.platform]


def test_phase_qualified_name_helper_round_trips():
    """``session_naming`` exposes a phase-qualified naming helper that encodes
    issue + phase + persona, and a parser that recovers them."""
    compute = getattr(session_naming, "compute_phase_surface_name", None)
    assert compute is not None, (
        "session_naming has no compute_phase_surface_name helper — there is "
        "no phase-qualified surface name"
    )

    red_name = compute("ATDD", 746, "RED", "tester")
    assert "746" in red_name and "RED" in red_name and "tester" in red_name, (
        f"phase-qualified name {red_name!r} does not encode issue/phase/persona"
    )
    assert "·" in red_name, (
        f"phase-qualified name {red_name!r} is not segmented with '·'"
    )

    green_name = compute("ATDD", 746, "GREEN", "coder")
    assert green_name != red_name, (
        "phase-qualified names for RED/tester and GREEN/coder are identical"
    )

    parse = getattr(session_naming, "parse_phase_surface_name", None)
    assert parse is not None, (
        "session_naming has no parse_phase_surface_name helper — the "
        "phase-qualified name does not round-trip"
    )
    parsed = parse(red_name)
    assert parsed is not None, f"phase-qualified name {red_name!r} did not parse"
    assert getattr(parsed, "issue", None) == 746
    assert str(getattr(parsed, "phase", "")).upper() == "RED"
    assert getattr(parsed, "persona", None) == "tester"


def test_transition_renames_worker_surface_to_phase_qualified_name(
    tmp_path, monkeypatch
):
    """The RED transition renames the worker surface to a phase-qualified name
    encoding the RED phase and the tester persona."""
    fake_mx = FakeRespawnMx()
    spawn_handler = patch_spawn_env(tmp_path, monkeypatch, fake_mx)
    ctx = CoachContext(issue_number=746, multiplexer_mode="pane")

    assert spawn_handler.handle(
        ctx, Transition(src=Phase.INIT, dst=Phase.PLANNED)
    ) == HandlerResult.HANDLED
    assert spawn_handler.handle(
        ctx, Transition(src=Phase.PLANNED, dst=Phase.RED)
    ) == HandlerResult.HANDLED

    renames = [c["name"] or "" for c in fake_mx.ops("rename")]
    assert any(
        "RED" in name and "tester" in name for name in renames
    ), (
        "no rename to a phase-qualified RED/tester name was issued on the "
        f"RED transition — renames recorded: {renames}"
    )
