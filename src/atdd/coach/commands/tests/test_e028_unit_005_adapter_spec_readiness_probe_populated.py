# URN: test:spawn-agents:E028-UNIT-005-adapter-spec-readiness-probe-populated
# Acceptance: acc:spawn-agents:E028-UNIT-005-adapter-spec-readiness-probe-populated
# WMBT: wmbt:spawn-agents:E028
# Phase: GREEN
# Layer: backend.unit
# Runtime: python
# Assertion: behavioral
"""E028-UNIT-005 — Every AdapterSpec in ADAPTER_REGISTRY has readiness_probe; claude-code uses SurfaceMarkerProbe with '❯'

RED: fails with ImportError (SurfaceMarkerProbe) then AttributeError (readiness_probe field) until E022 GREEN phase.
"""
from __future__ import annotations


def test_adapter_spec_readiness_probe_populated():
    from atdd.coach.commands.spawn import (  # ImportError until GREEN
        ADAPTER_REGISTRY,
        ProcessAlivePlusDelayProbe,
        SurfaceMarkerProbe,
    )

    # Every registered adapter must carry a non-None readiness_probe
    for adapter_id, config in ADAPTER_REGISTRY.items():
        assert config.readiness_probe is not None, (
            f"ADAPTER_REGISTRY[{adapter_id!r}].readiness_probe is None — "
            f"E022 requires every adapter to have a readiness probe"
        )

    # claude-code specifically uses SurfaceMarkerProbe with '❯' in markers
    cc_probe = ADAPTER_REGISTRY["claude-code"].readiness_probe
    assert isinstance(cc_probe, SurfaceMarkerProbe), (
        f"ADAPTER_REGISTRY['claude-code'].readiness_probe is {type(cc_probe)!r}, "
        f"expected SurfaceMarkerProbe"
    )
    assert "❯" in cc_probe.markers, (
        f"claude-code SurfaceMarkerProbe.markers={cc_probe.markers!r} — '❯' must be present"
    )

    # All non-claude-code adapters use ProcessAlivePlusDelayProbe (generic fallback)
    for adapter_id in ("claude-glm", "claude-gpt", "codex", "gemini"):
        probe = ADAPTER_REGISTRY[adapter_id].readiness_probe
        assert isinstance(probe, ProcessAlivePlusDelayProbe), (
            f"ADAPTER_REGISTRY[{adapter_id!r}].readiness_probe is {type(probe)!r}, "
            f"expected ProcessAlivePlusDelayProbe"
        )
