# URN: test:govern-projection-fields:mark-object-tombstone:K001-UNIT-001-red-tombstoned-object-revived
# Acceptance: acc:govern-projection-fields:K001-UNIT-001-red-tombstoned-object-revived
# WMBT: wmbt:govern-projection-fields:K001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:govern-projection-fields:K001-UNIT-001-red-tombstoned-object-revived — fails until the govern-projection-fields wagon implements it. Refs #1400.
"""RED skeleton for acc:govern-projection-fields:K001-UNIT-001-red-tombstoned-object-revived.

wagon: govern-projection-fields | feature: mark-object-tombstone | phase: RED
WMBT: wmbt:govern-projection-fields:K001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the govern-projection-fields wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="govern-projection-fields not yet implemented (RED; #1400)")
def test_k001_unit_001_red_tombstoned_object_revived() -> None:
    """K001-UNIT-001-red-tombstoned-object-revived — behaviour not yet implemented."""
    raise AssertionError(
        "RED: govern-projection-fields acceptance acc:govern-projection-fields:K001-UNIT-001-red-tombstoned-object-revived is not implemented yet"
    )
