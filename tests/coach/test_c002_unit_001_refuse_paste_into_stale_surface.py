# URN: test:spawn-agents:coach-spawn-respawn-reliability-primitives:C002-UNIT-001-refuse-paste-into-stale-surface
# Acceptance: acc:spawn-agents:C002-UNIT-001-refuse-paste-into-stale-surface
# WMBT: wmbt:spawn-agents:C002
# Phase: GREEN
# Layer: backend.application
# Assertion: behavioral
"""C002-UNIT-001 — when the issue's resolved surface is not live (stale), the
guard never pastes into it (closes 'pasted into a stale surface so the worker
never became live').

RED: fails until ``guarded_paste`` exists in ``atdd.coach.surface_guard`` and
refuses / re-creates rather than pasting into a dead ref.
"""
from __future__ import annotations

import pytest

from tests.coach._respawn_reliability_helpers import FakeSurfaceRegistry

pytestmark = [pytest.mark.coder]


def test_no_paste_into_stale_surface():
    from atdd.coach.surface_guard import guarded_paste

    # No live surfaces bound to the issue — the only known ref is stale.
    registry = FakeSurfaceRegistry(live=[])
    guarded_paste(1079, "launch prompt", registry)

    stale_pastes = [ref for ref, _ in registry.pastes if not registry.is_live(ref) and ref not in registry.created]
    assert stale_pastes == [], f"nothing should be pasted into a stale ref: {registry.pastes}"


def test_creates_a_fresh_live_surface_when_none_live():
    from atdd.coach.surface_guard import guarded_paste

    registry = FakeSurfaceRegistry(live=[])
    outcome = guarded_paste(1079, "launch prompt", registry)

    assert registry.created, "a fresh live surface must be created when none is live"
    # The paste (if any) must land on the freshly created live surface.
    if registry.pastes:
        pasted_ref = registry.pastes[-1][0]
        assert pasted_ref in registry.created
    assert getattr(outcome, "refused", False) is False
