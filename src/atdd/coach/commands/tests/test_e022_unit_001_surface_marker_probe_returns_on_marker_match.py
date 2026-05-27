# URN: test:spawn-agents:E022-UNIT-001-surface-marker-probe-returns-on-marker-match
# Acceptance: acc:spawn-agents:E022-UNIT-001-surface-marker-probe-returns-on-marker-match
# WMBT: wmbt:spawn-agents:E022
# Phase: GREEN
# Layer: backend.unit
# Runtime: python
# Assertion: behavioral
"""E022-UNIT-001 — SurfaceMarkerProbe.wait_for_ready returns without error when marker in surface text

RED: fails with ImportError — SurfaceMarkerProbe does not exist until E022 GREEN phase.
"""
from __future__ import annotations

import time


class _PromptReadyMux:
    """FakeMultiplexer that reports the claude-code prompt marker immediately."""

    def capture_pane_text(self, surface_ref: str) -> str:
        return "❯ "


def test_surface_marker_probe_returns_on_marker_match():
    from atdd.coach.commands.spawn import SurfaceMarkerProbe  # ImportError until GREEN

    mux = _PromptReadyMux()
    probe = SurfaceMarkerProbe(markers=["❯", "◆"])

    t0 = time.monotonic()
    probe.wait_for_ready(
        surface_ref="surface:1",
        multiplexer=mux,
        timeout_s=2.0,
        poll_interval_s=0.01,
    )
    elapsed = time.monotonic() - t0

    assert elapsed < 1.0, (
        f"SurfaceMarkerProbe took {elapsed:.3f}s — marker '❯' should be found on first poll"
    )
