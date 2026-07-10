# URN: test:enforce-merge-authority:enforce-rule-disposition:C004-SMOKE-001-advisory-disposition-on-a-new-rule
# Acceptance: acc:enforce-merge-authority:C004-SMOKE-001-advisory-disposition-on-a-new-rule
# WMBT: wmbt:enforce-merge-authority:C004
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:enforce-merge-authority:C004-SMOKE-001-advisory-disposition-on-a-new-rule — fails until the enforce-merge-authority wagon implements it. Refs #1400.
"""RED skeleton for acc:enforce-merge-authority:C004-SMOKE-001-advisory-disposition-on-a-new-rule.

wagon: enforce-merge-authority | feature: enforce-rule-disposition | phase: SMOKE
WMBT: wmbt:enforce-merge-authority:C004

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the enforce-merge-authority wagon lands the behaviour (advisory-disposition-on-a-new-rule holds end-to-end against real infrastructure). When it
xpasses, drop the xfail marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest

@pytest.mark.smoke
@pytest.mark.xfail(strict=True, reason="enforce-merge-authority not yet implemented (RED; #1400)")
def test_c004_smoke_001_advisory_disposition_on_a_new_rule(tmp_path) -> None:
    """C004-SMOKE-001-advisory-disposition-on-a-new-rule — behaviour not yet implemented."""
    raise AssertionError(
        "RED: enforce-merge-authority acceptance acc:enforce-merge-authority:C004-SMOKE-001-advisory-disposition-on-a-new-rule is not implemented yet"
    )
