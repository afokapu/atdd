# URN: test:reconcile-local-store:guard-dirty-store:C001-SMOKE-001-dirty-store-overwrite
# Acceptance: acc:reconcile-local-store:C001-SMOKE-001-dirty-store-overwrite
# WMBT: wmbt:reconcile-local-store:C001
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:reconcile-local-store:C001-SMOKE-001-dirty-store-overwrite — fails until the reconcile-local-store wagon implements it (train 0006). Refs #1400.
"""RED skeleton for acc:reconcile-local-store:C001-SMOKE-001-dirty-store-overwrite.

wagon: reconcile-local-store | feature: guard-dirty-store | phase: RED
WMBT: wmbt:reconcile-local-store:C001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the reconcile-local-store wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.smoke
@pytest.mark.xfail(strict=True, reason="reconcile-local-store not yet implemented (RED; #1400)")
def test_c001_smoke_001_dirty_store_overwrite(tmp_path) -> None:
    """C001-SMOKE-001-dirty-store-overwrite — behaviour not yet implemented."""
    raise AssertionError(
        "RED: reconcile-local-store acceptance acc:reconcile-local-store:C001-SMOKE-001-dirty-store-overwrite is not implemented yet"
    )
