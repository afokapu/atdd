# URN: test:govern-lifecycle:enforcing-phase-transition-gate:C017-UNIT-001-agent-edge-listed-in-gate-transitions-is-a-violation
# Acceptance: acc:govern-lifecycle:C017-UNIT-001-agent-edge-listed-in-gate-transitions-is-a-violation
# WMBT: wmbt:govern-lifecycle:C017
# Phase: RED
# Layer: application
"""C017-UNIT-001 — the resolver reports an agent edge the config gates.

Synthetic tables on purpose: the real ones are the smoke acceptance's job, and a
detector proved only against live data cannot show it stays quiet on the shapes
that are correct.
"""
from __future__ import annotations

from ._c017_gate_autonomy import operator_gated_agent_edges

_PHASES = {
    "PLANNED": {"autonomy": "operator"},
    "GREEN": {"autonomy": "agent"},
    "SMOKE": {"autonomy": "agent"},
}


def test_agent_edge_that_config_gates_is_reported():
    found = operator_gated_agent_edges(
        _PHASES, {"SMOKE->REFACTOR": True, "PLANNED->RED": True}
    )
    assert found == ["SMOKE->REFACTOR"], (
        "the resolver must report an edge the machine calls agent-submittable "
        f"while config gates it; got {found}"
    )


def test_correct_shapes_are_not_reported():
    # operator edge, gated -> the convention working as intended
    assert operator_gated_agent_edges(_PHASES, {"PLANNED->RED": True}) == []
    # agent edge, explicitly ungated -> an ungating, not a gate
    assert operator_gated_agent_edges(_PHASES, {"SMOKE->REFACTOR": False}) == []
    # agent edge, absent entirely
    assert operator_gated_agent_edges(_PHASES, {}) == []
    # unknown FROM phase must not crash or be invented into a violation
    assert operator_gated_agent_edges(_PHASES, {"NOPE->GONE": True}) == []
