# URN: test:spawn-agents:coach-spawn-respawn-reliability-primitives:E032-UNIT-002-noop-when-already-at-target
# Acceptance: acc:spawn-agents:E032-UNIT-002-noop-when-already-at-target
# WMBT: wmbt:spawn-agents:E032
# Phase: GREEN
# Layer: backend.application
# Assertion: behavioral
"""E032-UNIT-002 — when the issue is already at the target phase the advance is a
no-op: no label mutation, no error (re-firing the same transition is harmless).

RED: fails until ``advance_phase_label_idempotent`` reads the current phase and
short-circuits to a no-op when already at the target.
"""
from __future__ import annotations

import pytest

from tests.coach._respawn_reliability_helpers import FakeLabelStore

pytestmark = [pytest.mark.coder]


def test_already_at_target_is_noop_no_mutation():
    from atdd.coach.label_advance import advance_phase_label_idempotent

    store = FakeLabelStore(current="GREEN")
    outcome = advance_phase_label_idempotent(
        1079, source="RED", target="GREEN",
        read_phase=store.read_phase, swap_label=store.swap_label,
    )

    assert store.swaps == [], "no swap should fire when already at the target"
    assert store.current == "GREEN", "label set is unchanged"
    assert getattr(outcome, "status", None) == "noop"


def test_already_at_target_raises_no_exception():
    from atdd.coach.label_advance import advance_phase_label_idempotent

    store = FakeLabelStore(current="GREEN")
    # Must not raise — a re-fired transition is a safe no-op.
    advance_phase_label_idempotent(
        1079, source="RED", target="GREEN",
        read_phase=store.read_phase, swap_label=store.swap_label,
    )
