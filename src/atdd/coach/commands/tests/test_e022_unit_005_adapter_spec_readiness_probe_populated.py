# URN: test:spawn-agents:E022-UNIT-005-adapter-spec-readiness-probe-populated
# Acceptance: acc:spawn-agents:E022-UNIT-005-adapter-spec-readiness-probe-populated
# WMBT: wmbt:spawn-agents:E022
# Phase: GREEN
# Layer: backend.unit
# Runtime: python
# Assertion: behavioral
"""E022-UNIT-005 — Every AdapterSpec in ADAPTER_REGISTRY has readiness_probe; claude-code uses SurfaceMarkerProbe with '❯'

RED: fails until AdapterSpec.readiness_probe is implemented — pending E022 GREEN phase.
"""
from __future__ import annotations

import pytest


def test_adapter_spec_readiness_probe_populated():
    pytest.fail(
        "RED: Every AdapterSpec in ADAPTER_REGISTRY has readiness_probe; claude-code uses SurfaceMarkerProbe with '❯' — pending E022 GREEN phase"
    )
