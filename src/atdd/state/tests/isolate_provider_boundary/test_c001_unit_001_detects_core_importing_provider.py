# URN: test:isolate-provider-boundary:enforce-import-boundary:C001-UNIT-001-detects-core-importing-provider
# Acceptance: acc:isolate-provider-boundary:C001-UNIT-001-detects-core-importing-provider
# WMBT: wmbt:isolate-provider-boundary:C001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:isolate-provider-boundary:C001-UNIT-001-detects-core-importing-provider — fails until the isolate-provider-boundary wagon implements it. Refs #1400.
"""RED skeleton for acc:isolate-provider-boundary:C001-UNIT-001-detects-core-importing-provider.

wagon: isolate-provider-boundary | feature: enforce-import-boundary | phase: RED
WMBT: wmbt:isolate-provider-boundary:C001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the isolate-provider-boundary wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="isolate-provider-boundary not yet implemented (RED; #1400)")
def test_c001_unit_001_detects_core_importing_provider(tmp_path) -> None:
    """C001-UNIT-001-detects-core-importing-provider — behaviour not yet implemented."""
    raise AssertionError(
        "RED: isolate-provider-boundary acceptance acc:isolate-provider-boundary:C001-UNIT-001-detects-core-importing-provider is not implemented yet"
    )
