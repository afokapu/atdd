# URN: test:migrate-projection-authority:migrate-manifest-projection:C001-UNIT-002-reports-every-offending-entry
# Acceptance: acc:migrate-projection-authority:C001-UNIT-002-reports-every-offending-entry
# WMBT: wmbt:migrate-projection-authority:C001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:migrate-projection-authority:C001-UNIT-002-reports-every-offending-entry — fails until the migrate-projection-authority wagon implements it (train 0006). Refs #1400.
"""RED skeleton for acc:migrate-projection-authority:C001-UNIT-002-reports-every-offending-entry.

wagon: migrate-projection-authority | feature: migrate-manifest-projection | phase: RED
WMBT: wmbt:migrate-projection-authority:C001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the migrate-projection-authority wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="migrate-projection-authority not yet implemented (RED; #1400)")
def test_c001_unit_002_reports_every_offending_entry(tmp_path) -> None:
    """C001-UNIT-002-reports-every-offending-entry — behaviour not yet implemented."""
    raise AssertionError(
        "RED: migrate-projection-authority acceptance acc:migrate-projection-authority:C001-UNIT-002-reports-every-offending-entry is not implemented yet"
    )
