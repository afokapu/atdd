# URN: test:migrate-projection-authority:plan-migration-rollout:K001-UNIT-001-exit-criteria-unmet-before-cutover
# Acceptance: acc:migrate-projection-authority:K001-UNIT-001-exit-criteria-unmet-before-cutover
# WMBT: wmbt:migrate-projection-authority:K001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:migrate-projection-authority:K001-UNIT-001-exit-criteria-unmet-before-cutover — fails until the migrate-projection-authority wagon implements it (train 0006). Refs #1400.
"""RED skeleton for acc:migrate-projection-authority:K001-UNIT-001-exit-criteria-unmet-before-cutover.

wagon: migrate-projection-authority | feature: plan-migration-rollout | phase: RED
WMBT: wmbt:migrate-projection-authority:K001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the migrate-projection-authority wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="migrate-projection-authority not yet implemented (RED; #1400)")
def test_k001_unit_001_exit_criteria_unmet_before_cutover(tmp_path) -> None:
    """K001-UNIT-001-exit-criteria-unmet-before-cutover — behaviour not yet implemented."""
    raise AssertionError(
        "RED: migrate-projection-authority acceptance acc:migrate-projection-authority:K001-UNIT-001-exit-criteria-unmet-before-cutover is not implemented yet"
    )
