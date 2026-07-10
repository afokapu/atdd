# URN: test:enforce-merge-authority:define-required-checks:D002-UNIT-002-policy-pins-contexts-and-settings
# Acceptance: acc:enforce-merge-authority:D002-UNIT-002-policy-pins-contexts-and-settings
# WMBT: wmbt:enforce-merge-authority:D002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:enforce-merge-authority:D002-UNIT-002-policy-pins-contexts-and-settings — fails until the enforce-merge-authority wagon implements it. Refs #1400.
"""RED skeleton for acc:enforce-merge-authority:D002-UNIT-002-policy-pins-contexts-and-settings.

wagon: enforce-merge-authority | feature: define-required-checks | phase: RED
WMBT: wmbt:enforce-merge-authority:D002

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the enforce-merge-authority wagon lands the behaviour (the policy pins the exact required status-check contexts plus no-bypass and up-to-date settings). When it
xpasses, drop the xfail marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest

@pytest.mark.xfail(strict=True, reason="enforce-merge-authority not yet implemented (RED; #1400)")
def test_d002_unit_002_policy_pins_contexts_and_settings() -> None:
    """D002-UNIT-002-policy-pins-contexts-and-settings — behaviour not yet implemented."""
    raise AssertionError(
        "RED: enforce-merge-authority acceptance acc:enforce-merge-authority:D002-UNIT-002-policy-pins-contexts-and-settings is not implemented yet"
    )
