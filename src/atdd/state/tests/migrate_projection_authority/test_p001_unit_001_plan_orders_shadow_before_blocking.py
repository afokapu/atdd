# URN: test:migrate-projection-authority:plan-migration-rollout:P001-UNIT-001-plan-orders-shadow-before-blocking
# Acceptance: acc:migrate-projection-authority:P001-UNIT-001-plan-orders-shadow-before-blocking
# WMBT: wmbt:migrate-projection-authority:P001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:migrate-projection-authority:P001-UNIT-001-plan-orders-shadow-before-blocking — fails until the migrate-projection-authority wagon implements it (train 0006). Refs #1400.
"""RED skeleton for acc:migrate-projection-authority:P001-UNIT-001-plan-orders-shadow-before-blocking.

wagon: migrate-projection-authority | feature: plan-migration-rollout | phase: RED
WMBT: wmbt:migrate-projection-authority:P001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the migrate-projection-authority wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="migrate-projection-authority not yet implemented (RED; #1400)")
def test_p001_unit_001_plan_orders_shadow_before_blocking(tmp_path) -> None:
    """P001-UNIT-001-plan-orders-shadow-before-blocking — behaviour not yet implemented."""
    raise AssertionError(
        "RED: migrate-projection-authority acceptance acc:migrate-projection-authority:P001-UNIT-001-plan-orders-shadow-before-blocking is not implemented yet"
    )
