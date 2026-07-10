# URN: test:migrate-projection-authority:plan-migration-rollout:K001-SMOKE-001-collaborates-through-projection-only
# Acceptance: acc:migrate-projection-authority:K001-SMOKE-001-collaborates-through-projection-only
# WMBT: wmbt:migrate-projection-authority:K001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:migrate-projection-authority:K001-SMOKE-001-collaborates-through-projection-only — fails until the migrate-projection-authority wagon implements it (train 0006). Refs #1400.
"""RED skeleton for acc:migrate-projection-authority:K001-SMOKE-001-collaborates-through-projection-only.

wagon: migrate-projection-authority | feature: plan-migration-rollout | phase: SMOKE
WMBT: wmbt:migrate-projection-authority:K001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the migrate-projection-authority wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.smoke
@pytest.mark.xfail(strict=True, reason="migrate-projection-authority not yet implemented (RED; #1400)")
def test_k001_smoke_001_collaborates_through_projection_only(tmp_path) -> None:
    """K001-SMOKE-001-collaborates-through-projection-only — behaviour not yet implemented."""
    raise AssertionError(
        "RED: migrate-projection-authority acceptance acc:migrate-projection-authority:K001-SMOKE-001-collaborates-through-projection-only is not implemented yet"
    )
