# URN: test:spawn-agents:coach-spawn-step-by-step-verify-each-stage:E011-UNIT-001-verify-stage-raises-rename-not-accepted
# Acceptance: acc:spawn-agents:E011-UNIT-001-verify-stage-raises-rename-not-accepted
# WMBT: wmbt:spawn-agents:E011
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
"""E011-UNIT-001 — _verify_stage raises RenameNotAccepted when capture_pane_text
never returns the canonical name within the timeout.

RED: _verify_stage, RenameNotAccepted, and capture_pane_text do not exist yet.
The current code fire-and-forgets /rename without any post-condition probe (issue #799).
"""
from __future__ import annotations

import pytest


class _NeverRenamesMux:
    """capture_pane_text always returns a generic idle screen — rename never lands."""

    def capture_pane_text(self, surface_ref: str) -> str:
        return "Press Enter to send"


def test_verify_stage_raises_rename_not_accepted_on_timeout():
    from atdd.coach.commands.spawn import (
        RenameNotAccepted,
        _verify_stage,
    )

    mux = _NeverRenamesMux()
    with pytest.raises(RenameNotAccepted):
        _verify_stage(
            stage_name="rename-accepted",
            surface_ref="surface:1",
            backend=mux,
            expect_any=("ATDD42",),
            timeout_s=0.1,
            poll_interval_s=0.01,
        )


def test_verify_stage_passes_when_canonical_name_in_capture():
    from atdd.coach.commands.spawn import _verify_stage

    class _RenamedMux:
        def capture_pane_text(self, surface_ref: str) -> str:
            return "ATDD42 · ⏺ Thinking..."

    _verify_stage(
        stage_name="rename-accepted",
        surface_ref="surface:1",
        backend=_RenamedMux(),
        expect_any=("ATDD42",),
        timeout_s=1.0,
        poll_interval_s=0.01,
    )


def test_rename_not_accepted_is_a_worker_readiness_timeout():
    """RenameNotAccepted should subclass WorkerReadinessTimeout for consistent handling."""
    from atdd.coach.commands.spawn import RenameNotAccepted, WorkerReadinessTimeout

    assert issubclass(RenameNotAccepted, WorkerReadinessTimeout)
