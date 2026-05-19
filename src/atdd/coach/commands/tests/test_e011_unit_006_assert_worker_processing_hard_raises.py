# URN: test:spawn-agents:coach-spawn-step-by-step-verify-each-stage:E011-UNIT-006-assert-worker-processing-hard-raises
# Acceptance: acc:spawn-agents:E011-UNIT-006-assert-worker-processing-hard-raises
# WMBT: wmbt:spawn-agents:E011
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
"""E011-UNIT-006 — _assert_worker_processing raises WorkerReadinessTimeout instead
of silently returning when the backend exposes capture_pane_text but the pane
never shows a processing indicator.

RED: The current code silently skips when the backend lacks capture_surface_text.
After E011, backends that DO implement capture_pane_text must cause a hard raise
on timeout — the silent-skip escape hatch is removed (issue #799).
"""
from __future__ import annotations

import pytest


class _AlwaysIdleMux:
    """Backend with capture_pane_text that always returns an idle state."""

    def capture_pane_text(self, surface_ref: str) -> str:
        return "Press up to edit queued messages"


def test_assert_worker_processing_hard_raises_when_pane_always_idle():
    from atdd.coach.commands.spawn import WorkerReadinessTimeout, _assert_worker_processing

    mux = _AlwaysIdleMux()
    with pytest.raises(WorkerReadinessTimeout):
        _assert_worker_processing(
            surface_ref="surface:5",
            multiplexer=mux,
            timeout_s=0.1,
            poll_interval_s=0.01,
        )


def test_assert_worker_processing_no_longer_skips_silently():
    """When backend implements capture_pane_text, a timeout must ALWAYS raise."""
    from atdd.coach.commands.spawn import WorkerReadinessTimeout, _assert_worker_processing

    class _CapturePanePresent:
        """Implements capture_pane_text but never returns a processing signal."""

        def capture_pane_text(self, surface_ref: str) -> str:
            return "Press Enter to send"

    with pytest.raises(WorkerReadinessTimeout):
        _assert_worker_processing(
            surface_ref="surface:7",
            multiplexer=_CapturePanePresent(),
            timeout_s=0.1,
            poll_interval_s=0.01,
        )
