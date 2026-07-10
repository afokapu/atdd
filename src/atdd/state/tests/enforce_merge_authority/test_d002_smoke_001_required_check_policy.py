# URN: test:enforce-merge-authority:define-required-checks:D002-SMOKE-001-required-check-policy
# Acceptance: acc:enforce-merge-authority:D002-SMOKE-001-required-check-policy
# WMBT: wmbt:enforce-merge-authority:D002
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:enforce-merge-authority:D002-SMOKE-001-required-check-policy — fails until the enforce-merge-authority wagon implements it. Refs #1400.
"""RED skeleton for acc:enforce-merge-authority:D002-SMOKE-001-required-check-policy.

wagon: enforce-merge-authority | feature: define-required-checks | phase: SMOKE
WMBT: wmbt:enforce-merge-authority:D002

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the enforce-merge-authority wagon lands the behaviour (required-check-policy holds end-to-end against real branch-protection infrastructure). When it
xpasses, drop the xfail marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest

@pytest.mark.smoke
@pytest.mark.xfail(strict=True, reason="enforce-merge-authority not yet implemented (RED; #1400)")
def test_d002_smoke_001_required_check_policy(tmp_path) -> None:
    """D002-SMOKE-001-required-check-policy — behaviour not yet implemented."""
    raise AssertionError(
        "RED: enforce-merge-authority acceptance acc:enforce-merge-authority:D002-SMOKE-001-required-check-policy is not implemented yet"
    )
