# URN: test:spawn-agents:spawn-time-non-interactive-convention:E013-SMOKE-001-live-adapter-registry-passes-layer-b-validator
# Acceptance: acc:spawn-agents:E013-SMOKE-001-live-adapter-registry-passes-layer-b-validator
# WMBT: wmbt:spawn-agents:E013
# Phase: SMOKE
# Layer: smoke
# Runtime: python
# Assertion: behavioral
"""E013-SMOKE-001 — the live ADAPTER_REGISTRY imported from spawn.py passes
check_adapter_registry_fields with zero violations.

SMOKE: exercises the actual deployed ADAPTER_REGISTRY, not a synthetic fixture.
"""
from __future__ import annotations

import pytest


@pytest.mark.smoke
def test_live_adapter_registry_passes_layer_b_validator():
    from atdd.coach.commands.spawn import ADAPTER_REGISTRY
    from atdd.coach.validators.test_spawn_non_interactive_validator import (
        check_adapter_registry_fields,
    )

    violations = check_adapter_registry_fields(ADAPTER_REGISTRY)
    assert not violations, (
        "E013-SMOKE-001: live ADAPTER_REGISTRY has Layer-B violations:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )
