# URN: test:spawn-agents:coach-spawn-respawn-reliability-primitives:C002-UNIT-003-happy-path-single-live-surface-paste
# Acceptance: acc:spawn-agents:C002-UNIT-003-happy-path-single-live-surface-paste
# WMBT: wmbt:spawn-agents:C002
# Phase: GREEN
# Layer: backend.application
# Assertion: behavioral
"""C002-UNIT-003 — when exactly one live surface is bound to the issue, the guard
pastes into it and creates nothing new (the normal path is unchanged).

RED: fails until ``guarded_paste`` pastes into the single live surface.
"""
from __future__ import annotations

import pytest

from tests.coach._respawn_reliability_helpers import FakeSurfaceRegistry

pytestmark = [pytest.mark.coder]


def test_single_live_surface_is_paste_target_no_creation():
    from atdd.coach.surface_guard import guarded_paste

    registry = FakeSurfaceRegistry(live=["surface-only"])
    outcome = guarded_paste(1079, "launch prompt", registry)

    assert registry.pastes == [("surface-only", "launch prompt")], (
        f"paste must target the single live surface: {registry.pastes}"
    )
    assert registry.created == [], "no new surface should be created on the happy path"
    assert registry.reaped == [], "nothing to reap when exactly one is live"
    assert getattr(outcome, "refused", False) is False
    assert len(registry.live_surfaces_for(1079)) == 1
