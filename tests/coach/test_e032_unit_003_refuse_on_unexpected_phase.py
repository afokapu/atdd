# URN: test:spawn-agents:coach-spawn-respawn-reliability-primitives:E032-UNIT-003-refuse-on-unexpected-phase
# Acceptance: acc:spawn-agents:E032-UNIT-003-refuse-on-unexpected-phase
# WMBT: wmbt:spawn-agents:E032
# Phase: GREEN
# Layer: backend.application
# Assertion: behavioral
"""E032-UNIT-003 — when the issue is at a phase that is neither source nor
target, the advance refuses instead of overwriting (no silent clobber).

RED: fails until ``advance_phase_label_idempotent`` refuses (no mutation) on an
unexpected current phase and names current-vs-expected.
"""
from __future__ import annotations

import pytest

from tests.coach._respawn_reliability_helpers import FakeLabelStore

pytestmark = [pytest.mark.coder]


def test_unexpected_phase_refuses_without_mutation():
    from atdd.coach.label_advance import advance_phase_label_idempotent

    # Issue sits at SMOKE; the requested transition is RED -> GREEN.
    store = FakeLabelStore(current="SMOKE")
    outcome = advance_phase_label_idempotent(
        1079, source="RED", target="GREEN",
        read_phase=store.read_phase, swap_label=store.swap_label,
    )

    assert store.swaps == [], "no label mutation on an unexpected current phase"
    assert store.current == "SMOKE", "the existing label is left intact (no overwrite)"
    assert getattr(outcome, "status", None) == "refused"


def test_refusal_names_current_and_expected():
    from atdd.coach.label_advance import advance_phase_label_idempotent

    store = FakeLabelStore(current="SMOKE")
    outcome = advance_phase_label_idempotent(
        1079, source="RED", target="GREEN",
        read_phase=store.read_phase, swap_label=store.swap_label,
    )

    assert getattr(outcome, "current", None) == "SMOKE"
    assert getattr(outcome, "expected", None) == "RED"
