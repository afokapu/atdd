# URN: test:govern-projection-fields:mark-object-tombstone:K001-UNIT-002-green-tombstone-is-a-record-not-a-deletion
# Acceptance: acc:govern-projection-fields:K001-UNIT-002-green-tombstone-is-a-record-not-a-deletion
# WMBT: wmbt:govern-projection-fields:K001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:govern-projection-fields:K001-UNIT-002-green-tombstone-is-a-record-not-a-deletion — fails until the govern-projection-fields wagon implements it. Refs #1400.
"""RED skeleton for acc:govern-projection-fields:K001-UNIT-002-green-tombstone-is-a-record-not-a-deletion.

wagon: govern-projection-fields | feature: mark-object-tombstone | phase: RED
WMBT: wmbt:govern-projection-fields:K001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the govern-projection-fields wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="govern-projection-fields not yet implemented (RED; #1400)")
def test_k001_unit_002_green_tombstone_is_a_record_not_a_deletion() -> None:
    """K001-UNIT-002-green-tombstone-is-a-record-not-a-deletion — behaviour not yet implemented."""
    raise AssertionError(
        "RED: govern-projection-fields acceptance acc:govern-projection-fields:K001-UNIT-002-green-tombstone-is-a-record-not-a-deletion is not implemented yet"
    )
