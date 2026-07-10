# URN: test:enforce-merge-authority:verify-trailer-diff:C002-UNIT-001-untrailed-projection-diff-is-admitted
# Acceptance: acc:enforce-merge-authority:C002-UNIT-001-untrailed-projection-diff-is-admitted
# WMBT: wmbt:enforce-merge-authority:C002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:enforce-merge-authority:C002-UNIT-001-untrailed-projection-diff-is-admitted — fails until the enforce-merge-authority wagon implements it. Refs #1400.
"""RED skeleton for acc:enforce-merge-authority:C002-UNIT-001-untrailed-projection-diff-is-admitted.

wagon: enforce-merge-authority | feature: verify-trailer-diff | phase: RED
WMBT: wmbt:enforce-merge-authority:C002

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the enforce-merge-authority wagon lands the behaviour (a projection object diff carrying no ATDD-Object trailer is rejected by the cross-check). When it
xpasses, drop the xfail marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest

@pytest.mark.xfail(strict=True, reason="enforce-merge-authority not yet implemented (RED; #1400)")
def test_c002_unit_001_untrailed_projection_diff_is_admitted() -> None:
    """C002-UNIT-001-untrailed-projection-diff-is-admitted — behaviour not yet implemented."""
    raise AssertionError(
        "RED: enforce-merge-authority acceptance acc:enforce-merge-authority:C002-UNIT-001-untrailed-projection-diff-is-admitted is not implemented yet"
    )
