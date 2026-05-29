# URN: test:spawn-agents:E028-UNIT-002-surface-marker-probe-raises-timeout-on-no-match
# Acceptance: acc:spawn-agents:E028-UNIT-002-surface-marker-probe-raises-timeout-on-no-match
# WMBT: wmbt:spawn-agents:E028
# Phase: GREEN
# Layer: backend.unit
# Runtime: python
# Assertion: behavioral
"""E028-UNIT-002 — SurfaceMarkerProbe.wait_for_ready raises WorkerReadinessTimeout when no marker appears

RED: fails with ImportError — SurfaceMarkerProbe does not exist until E022 GREEN phase.
"""
from __future__ import annotations

import pytest


class _EmptyMux:
    """FakeMultiplexer that never shows any prompt marker (TUI not ready)."""

    def capture_pane_text(self, surface_ref: str) -> str:
        return ""


def test_surface_marker_probe_raises_timeout_on_no_match():
    from atdd.coach.commands.spawn import (  # ImportError until GREEN
        SurfaceMarkerProbe,
        WorkerReadinessTimeout,
    )

    mux = _EmptyMux()
    probe = SurfaceMarkerProbe(markers=["❯", "◆"])

    with pytest.raises(WorkerReadinessTimeout) as exc_info:
        probe.wait_for_ready(
            surface_ref="surface:1",
            multiplexer=mux,
            timeout_s=0.05,
            poll_interval_s=0.01,
        )

    msg = str(exc_info.value)
    assert "surface:1" in msg, (
        f"WorkerReadinessTimeout message should contain the surface_ref. Got: {msg!r}"
    )
    assert "❯" in msg or "◆" in msg, (
        f"WorkerReadinessTimeout message should name the markers that were awaited. Got: {msg!r}"
    )
