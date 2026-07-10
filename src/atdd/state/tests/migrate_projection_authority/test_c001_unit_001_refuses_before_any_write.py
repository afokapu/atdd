# URN: test:migrate-projection-authority:migrate-manifest-projection:C001-UNIT-001-refuses-before-any-write
# Acceptance: acc:migrate-projection-authority:C001-UNIT-001-refuses-before-any-write
# WMBT: wmbt:migrate-projection-authority:C001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:migrate-projection-authority:C001-UNIT-001-refuses-before-any-write — fails until the migrate-projection-authority wagon implements it (train 0006). Refs #1400.
"""RED skeleton for acc:migrate-projection-authority:C001-UNIT-001-refuses-before-any-write.

wagon: migrate-projection-authority | feature: migrate-manifest-projection | phase: RED
WMBT: wmbt:migrate-projection-authority:C001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the migrate-projection-authority wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="migrate-projection-authority not yet implemented (RED; #1400)")
def test_c001_unit_001_refuses_before_any_write(tmp_path) -> None:
    """C001-UNIT-001-refuses-before-any-write — behaviour not yet implemented."""
    raise AssertionError(
        "RED: migrate-projection-authority acceptance acc:migrate-projection-authority:C001-UNIT-001-refuses-before-any-write is not implemented yet"
    )
