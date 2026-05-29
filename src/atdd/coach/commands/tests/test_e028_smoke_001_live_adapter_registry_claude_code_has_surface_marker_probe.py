# URN: test:spawn-agents:E028-SMOKE-001-live-adapter-registry-claude-code-has-surface-marker-probe
# Acceptance: acc:spawn-agents:E028-SMOKE-001-live-adapter-registry-claude-code-has-surface-marker-probe
# WMBT: wmbt:spawn-agents:E028
# Phase: SMOKE
# Layer: backend.smoke
# Runtime: python
# Assertion: behavioral
"""E028-SMOKE-001 — Deployed ADAPTER_REGISTRY claude-code entry has SurfaceMarkerProbe with '❯' in markers

RED: fails until SurfaceMarkerProbe is implemented — pending E022 GREEN phase.
"""
from __future__ import annotations

import os

import pytest

pytestmark = [pytest.mark.smoke]


@pytest.mark.skipif(
    not os.environ.get("ATDD_RUN_SMOKE"),
    reason="E028-SMOKE-001 requires ATDD_RUN_SMOKE=1",
)
def test_live_adapter_registry_claude_code_has_surface_marker_probe():
    from atdd.coach.commands.spawn import (  # ImportError until GREEN
        ADAPTER_REGISTRY,
        SurfaceMarkerProbe,
    )

    probe = ADAPTER_REGISTRY["claude-code"].readiness_probe

    assert isinstance(probe, SurfaceMarkerProbe), (
        f"claude-code readiness_probe is {type(probe)!r}, expected SurfaceMarkerProbe"
    )
    assert "❯" in probe.markers, (
        f"claude-code SurfaceMarkerProbe.markers={probe.markers!r} — '❯' must be present"
    )
