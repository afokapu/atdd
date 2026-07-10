# URN: test:isolate-provider-boundary:enforce-import-boundary:C001-SMOKE-001-core-provider-import
# Acceptance: acc:isolate-provider-boundary:C001-SMOKE-001-core-provider-import
# WMBT: wmbt:isolate-provider-boundary:C001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:isolate-provider-boundary:C001-SMOKE-001-core-provider-import — fails until the isolate-provider-boundary wagon implements it. Refs #1400.
"""RED skeleton for acc:isolate-provider-boundary:C001-SMOKE-001-core-provider-import.

wagon: isolate-provider-boundary | feature: enforce-import-boundary | phase: SMOKE
WMBT: wmbt:isolate-provider-boundary:C001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the isolate-provider-boundary wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.smoke
@pytest.mark.xfail(strict=True, reason="isolate-provider-boundary not yet implemented (RED; #1400)")
def test_c001_smoke_001_core_provider_import(tmp_path) -> None:
    """C001-SMOKE-001-core-provider-import — behaviour not yet implemented."""
    raise AssertionError(
        "RED: isolate-provider-boundary acceptance acc:isolate-provider-boundary:C001-SMOKE-001-core-provider-import is not implemented yet"
    )
