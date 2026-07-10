# URN: test:migrate-projection-authority:compare-shadow-projection:M001-UNIT-002-clean-repo-reports-no-drift
# Acceptance: acc:migrate-projection-authority:M001-UNIT-002-clean-repo-reports-no-drift
# WMBT: wmbt:migrate-projection-authority:M001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:migrate-projection-authority:M001-UNIT-002-clean-repo-reports-no-drift — fails until the migrate-projection-authority wagon implements it (train 0006). Refs #1400.
"""RED skeleton for acc:migrate-projection-authority:M001-UNIT-002-clean-repo-reports-no-drift.

wagon: migrate-projection-authority | feature: compare-shadow-projection | phase: RED
WMBT: wmbt:migrate-projection-authority:M001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the migrate-projection-authority wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="migrate-projection-authority not yet implemented (RED; #1400)")
def test_m001_unit_002_clean_repo_reports_no_drift(tmp_path) -> None:
    """M001-UNIT-002-clean-repo-reports-no-drift — behaviour not yet implemented."""
    raise AssertionError(
        "RED: migrate-projection-authority acceptance acc:migrate-projection-authority:M001-UNIT-002-clean-repo-reports-no-drift is not implemented yet"
    )
