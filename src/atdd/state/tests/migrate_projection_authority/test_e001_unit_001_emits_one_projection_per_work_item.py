# URN: test:migrate-projection-authority:migrate-manifest-projection:E001-UNIT-001-emits-one-projection-per-work-item
# Acceptance: acc:migrate-projection-authority:E001-UNIT-001-emits-one-projection-per-work-item
# WMBT: wmbt:migrate-projection-authority:E001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:migrate-projection-authority:E001-UNIT-001-emits-one-projection-per-work-item — fails until the migrate-projection-authority wagon implements it (train 0006). Refs #1400.
"""RED skeleton for acc:migrate-projection-authority:E001-UNIT-001-emits-one-projection-per-work-item.

wagon: migrate-projection-authority | feature: migrate-manifest-projection | phase: RED
WMBT: wmbt:migrate-projection-authority:E001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the migrate-projection-authority wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="migrate-projection-authority not yet implemented (RED; #1400)")
def test_e001_unit_001_emits_one_projection_per_work_item(tmp_path) -> None:
    """E001-UNIT-001-emits-one-projection-per-work-item — behaviour not yet implemented."""
    raise AssertionError(
        "RED: migrate-projection-authority acceptance acc:migrate-projection-authority:E001-UNIT-001-emits-one-projection-per-work-item is not implemented yet"
    )
