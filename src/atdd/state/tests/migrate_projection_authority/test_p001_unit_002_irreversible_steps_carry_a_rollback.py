# URN: test:migrate-projection-authority:plan-migration-rollout:P001-UNIT-002-irreversible-steps-carry-a-rollback
# Acceptance: acc:migrate-projection-authority:P001-UNIT-002-irreversible-steps-carry-a-rollback
# WMBT: wmbt:migrate-projection-authority:P001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:migrate-projection-authority:P001-UNIT-002-irreversible-steps-carry-a-rollback — fails until the migrate-projection-authority wagon implements it (train 0006). Refs #1400.
"""RED skeleton for acc:migrate-projection-authority:P001-UNIT-002-irreversible-steps-carry-a-rollback.

wagon: migrate-projection-authority | feature: plan-migration-rollout | phase: RED
WMBT: wmbt:migrate-projection-authority:P001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the migrate-projection-authority wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="migrate-projection-authority not yet implemented (RED; #1400)")
def test_p001_unit_002_irreversible_steps_carry_a_rollback(tmp_path) -> None:
    """P001-UNIT-002-irreversible-steps-carry-a-rollback — behaviour not yet implemented."""
    raise AssertionError(
        "RED: migrate-projection-authority acceptance acc:migrate-projection-authority:P001-UNIT-002-irreversible-steps-carry-a-rollback is not implemented yet"
    )
