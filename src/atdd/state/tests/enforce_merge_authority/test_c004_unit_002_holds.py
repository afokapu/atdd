# URN: test:enforce-merge-authority:enforce-rule-disposition:C004-UNIT-002-holds
# Acceptance: acc:enforce-merge-authority:C004-UNIT-002-holds
# WMBT: wmbt:enforce-merge-authority:C004
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:enforce-merge-authority:C004-UNIT-002-holds — fails until the enforce-merge-authority wagon implements it. Refs #1400.
"""RED skeleton for acc:enforce-merge-authority:C004-UNIT-002-holds.

wagon: enforce-merge-authority | feature: enforce-rule-disposition | phase: RED
WMBT: wmbt:enforce-merge-authority:C004

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the enforce-merge-authority wagon lands the behaviour (every authored convention node must ship disposition: strict unless a precondition and issue discharge advisory). When it
xpasses, drop the xfail marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest

@pytest.mark.xfail(strict=True, reason="enforce-merge-authority not yet implemented (RED; #1400)")
def test_c004_unit_002_holds() -> None:
    """C004-UNIT-002-holds — behaviour not yet implemented."""
    raise AssertionError(
        "RED: enforce-merge-authority acceptance acc:enforce-merge-authority:C004-UNIT-002-holds is not implemented yet"
    )
