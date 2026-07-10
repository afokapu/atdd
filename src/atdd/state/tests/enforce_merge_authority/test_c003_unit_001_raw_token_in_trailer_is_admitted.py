# URN: test:enforce-merge-authority:reject-history-secrets:C003-UNIT-001-raw-token-in-trailer-is-admitted
# Acceptance: acc:enforce-merge-authority:C003-UNIT-001-raw-token-in-trailer-is-admitted
# WMBT: wmbt:enforce-merge-authority:C003
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:enforce-merge-authority:C003-UNIT-001-raw-token-in-trailer-is-admitted — fails until the enforce-merge-authority wagon implements it. Refs #1400.
"""RED skeleton for acc:enforce-merge-authority:C003-UNIT-001-raw-token-in-trailer-is-admitted.

wagon: enforce-merge-authority | feature: reject-history-secrets | phase: RED
WMBT: wmbt:enforce-merge-authority:C003

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the enforce-merge-authority wagon lands the behaviour (a raw token in an ATDD trailer value reaches history unless the no-secrets validator rejects it). When it
xpasses, drop the xfail marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest

@pytest.mark.xfail(strict=True, reason="enforce-merge-authority not yet implemented (RED; #1400)")
def test_c003_unit_001_raw_token_in_trailer_is_admitted() -> None:
    """C003-UNIT-001-raw-token-in-trailer-is-admitted — behaviour not yet implemented."""
    raise AssertionError(
        "RED: enforce-merge-authority acceptance acc:enforce-merge-authority:C003-UNIT-001-raw-token-in-trailer-is-admitted is not implemented yet"
    )
