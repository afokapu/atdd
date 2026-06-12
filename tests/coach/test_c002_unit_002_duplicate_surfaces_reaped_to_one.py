# URN: test:spawn-agents:coach-spawn-respawn-reliability-primitives:C002-UNIT-002-duplicate-surfaces-reaped-to-one
# Acceptance: acc:spawn-agents:C002-UNIT-002-duplicate-surfaces-reaped-to-one
# WMBT: wmbt:spawn-agents:C002
# Phase: GREEN
# Layer: backend.application
# Assertion: behavioral
"""C002-UNIT-002 — when more than one live surface is bound to the same issue,
the guard converges to exactly one (reap or refuse), never pasting into an
arbitrary duplicate.

RED: fails until ``guarded_paste`` detects duplicates and reaps/refuses.
"""
from __future__ import annotations

import pytest

from tests.coach._respawn_reliability_helpers import FakeSurfaceRegistry

pytestmark = [pytest.mark.coder]


def test_duplicates_converge_to_one_or_refuse():
    from atdd.coach.surface_guard import guarded_paste

    registry = FakeSurfaceRegistry(live=["surface-A", "surface-B"])
    outcome = guarded_paste(1079, "launch prompt", registry)

    refused = getattr(outcome, "refused", False)
    remaining = registry.live_surfaces_for(1079)
    assert refused or len(remaining) == 1, (
        f"duplicates must be reaped to one or the paste refused; remaining={remaining}"
    )


def test_no_paste_into_arbitrary_duplicate_and_duplicate_recorded():
    from atdd.coach.surface_guard import guarded_paste

    registry = FakeSurfaceRegistry(live=["surface-A", "surface-B"])
    outcome = guarded_paste(1079, "launch prompt", registry)

    if getattr(outcome, "refused", False):
        assert registry.pastes == [], "a refusal must not paste anywhere"
    else:
        # Exactly one survivor; the paste (if any) targets that single survivor.
        survivors = registry.live_surfaces_for(1079)
        assert len(survivors) == 1
        for ref, _ in registry.pastes:
            assert ref in survivors, "must never paste into a reaped duplicate"
    assert getattr(outcome, "duplicate_detected", False) is True, (
        "the outcome must record that a duplicate condition was detected"
    )
