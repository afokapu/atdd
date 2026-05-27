# URN: test:spawn-agents:E022-UNIT-001-surface-marker-probe-returns-on-marker-match
# Acceptance: acc:spawn-agents:E022-UNIT-001-surface-marker-probe-returns-on-marker-match
# WMBT: wmbt:spawn-agents:E022
# Phase: GREEN
# Layer: backend.unit
# Runtime: python
# Assertion: behavioral
"""E022-UNIT-001 — SurfaceMarkerProbe.wait_for_ready returns without error when marker in surface text

RED: fails until SurfaceMarkerProbe is implemented — pending E022 GREEN phase.
"""
from __future__ import annotations

import pytest


def test_surface_marker_probe_returns_on_marker_match():
    pytest.fail(
        "RED: SurfaceMarkerProbe.wait_for_ready returns without error when marker in surface text — pending E022 GREEN phase"
    )
