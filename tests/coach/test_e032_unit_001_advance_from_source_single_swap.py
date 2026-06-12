# URN: test:spawn-agents:coach-spawn-respawn-reliability-primitives:E032-UNIT-001-advance-from-source-single-swap
# Acceptance: acc:spawn-agents:E032-UNIT-001-advance-from-source-single-swap
# WMBT: wmbt:spawn-agents:E032
# Phase: GREEN
# Layer: backend.application
# Assertion: behavioral
"""E032-UNIT-001 — from the expected source phase the advance performs exactly
one label swap (the normal happy path is unchanged).

RED: fails until ``advance_phase_label_idempotent`` exists in
``atdd.coach.label_advance`` and swaps exactly once when at the source phase.
"""
from __future__ import annotations

import pytest

from tests.coach._respawn_reliability_helpers import FakeLabelStore

pytestmark = [pytest.mark.coder]


def test_advance_from_source_swaps_once_and_reports_advanced():
    from atdd.coach.label_advance import advance_phase_label_idempotent

    store = FakeLabelStore(current="RED")
    outcome = advance_phase_label_idempotent(
        1079, source="RED", target="GREEN",
        read_phase=store.read_phase, swap_label=store.swap_label,
    )

    assert store.current == "GREEN", "issue ends at the target phase"
    assert store.swaps == ["GREEN"], "exactly one swap to the target was recorded"
    assert getattr(outcome, "status", None) == "advanced"
