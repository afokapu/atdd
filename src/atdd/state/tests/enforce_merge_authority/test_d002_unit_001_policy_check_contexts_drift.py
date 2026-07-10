# URN: test:enforce-merge-authority:define-required-checks:D002-UNIT-001-policy-check-contexts-drift
# Acceptance: acc:enforce-merge-authority:D002-UNIT-001-policy-check-contexts-drift
# WMBT: wmbt:enforce-merge-authority:D002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:enforce-merge-authority:D002-UNIT-001-policy-check-contexts-drift — fails until the enforce-merge-authority wagon implements it. Refs #1400.
"""RED skeleton for acc:enforce-merge-authority:D002-UNIT-001-policy-check-contexts-drift.

wagon: enforce-merge-authority | feature: define-required-checks | phase: RED
WMBT: wmbt:enforce-merge-authority:D002

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the enforce-merge-authority wagon lands the behaviour (a required-check policy whose contexts drift from the emitted status checks is rejected). When it
xpasses, drop the xfail marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest

@pytest.mark.xfail(strict=True, reason="enforce-merge-authority not yet implemented (RED; #1400)")
def test_d002_unit_001_policy_check_contexts_drift() -> None:
    """D002-UNIT-001-policy-check-contexts-drift — behaviour not yet implemented."""
    raise AssertionError(
        "RED: enforce-merge-authority acceptance acc:enforce-merge-authority:D002-UNIT-001-policy-check-contexts-drift is not implemented yet"
    )
