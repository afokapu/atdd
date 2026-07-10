# URN: test:govern-projection-fields:verify-merge-matrix:C002-UNIT-001-red-matrix-misses-cases
# Acceptance: acc:govern-projection-fields:C002-UNIT-001-red-matrix-misses-cases
# WMBT: wmbt:govern-projection-fields:C002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:govern-projection-fields:C002-UNIT-001-red-matrix-misses-cases — fails until the govern-projection-fields wagon implements it. Refs #1400.
"""RED skeleton for acc:govern-projection-fields:C002-UNIT-001-red-matrix-misses-cases.

wagon: govern-projection-fields | feature: verify-merge-matrix | phase: RED
WMBT: wmbt:govern-projection-fields:C002

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the govern-projection-fields wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="govern-projection-fields not yet implemented (RED; #1400)")
def test_c002_unit_001_red_matrix_misses_cases() -> None:
    """C002-UNIT-001-red-matrix-misses-cases — behaviour not yet implemented."""
    raise AssertionError(
        "RED: govern-projection-fields acceptance acc:govern-projection-fields:C002-UNIT-001-red-matrix-misses-cases is not implemented yet"
    )
