# URN: test:reconcile-local-store:guard-dirty-store:C001-UNIT-001-dirty-store-is-backed-up-not-overwritten
# Acceptance: acc:reconcile-local-store:C001-UNIT-001-dirty-store-is-backed-up-not-overwritten
# WMBT: wmbt:reconcile-local-store:C001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:reconcile-local-store:C001-UNIT-001-dirty-store-is-backed-up-not-overwritten — fails until the reconcile-local-store wagon implements it (train 0006). Refs #1400.
"""RED skeleton for acc:reconcile-local-store:C001-UNIT-001-dirty-store-is-backed-up-not-overwritten.

wagon: reconcile-local-store | feature: guard-dirty-store | phase: RED
WMBT: wmbt:reconcile-local-store:C001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the reconcile-local-store wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="reconcile-local-store not yet implemented (RED; #1400)")
def test_c001_unit_001_dirty_store_is_backed_up_not_overwritten(tmp_path) -> None:
    """C001-UNIT-001-dirty-store-is-backed-up-not-overwritten — behaviour not yet implemented."""
    raise AssertionError(
        "RED: reconcile-local-store acceptance acc:reconcile-local-store:C001-UNIT-001-dirty-store-is-backed-up-not-overwritten is not implemented yet"
    )
