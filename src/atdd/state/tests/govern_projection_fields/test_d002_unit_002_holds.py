# URN: test:govern-projection-fields:define-actor-ownership:D002-UNIT-002-holds
# Acceptance: acc:govern-projection-fields:D002-UNIT-002-holds
# WMBT: wmbt:govern-projection-fields:D002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:govern-projection-fields:D002-UNIT-002-holds — fails until the govern-projection-fields wagon implements it. Refs #1400.
"""RED skeleton for acc:govern-projection-fields:D002-UNIT-002-holds.

wagon: govern-projection-fields | feature: define-actor-ownership | phase: RED
WMBT: wmbt:govern-projection-fields:D002

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the govern-projection-fields wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="govern-projection-fields not yet implemented (RED; #1400)")
def test_d002_unit_002_holds() -> None:
    """D002-UNIT-002-holds — behaviour not yet implemented."""
    raise AssertionError(
        "RED: govern-projection-fields acceptance acc:govern-projection-fields:D002-UNIT-002-holds is not implemented yet"
    )
