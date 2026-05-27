# URN: test:spawn-agents:E022-UNIT-002-surface-marker-probe-raises-timeout-on-no-match
# Acceptance: acc:spawn-agents:E022-UNIT-002-surface-marker-probe-raises-timeout-on-no-match
# WMBT: wmbt:spawn-agents:E022
# Phase: GREEN
# Layer: backend.unit
# Runtime: python
# Assertion: behavioral
"""E022-UNIT-002 — SurfaceMarkerProbe.wait_for_ready raises WorkerReadinessTimeout when no marker appears

RED: fails until SurfaceMarkerProbe is implemented — pending E022 GREEN phase.
"""
from __future__ import annotations

import pytest


def test_surface_marker_probe_raises_timeout_on_no_match():
    pytest.fail(
        "RED: SurfaceMarkerProbe.wait_for_ready raises WorkerReadinessTimeout when no marker appears — pending E022 GREEN phase"
    )
