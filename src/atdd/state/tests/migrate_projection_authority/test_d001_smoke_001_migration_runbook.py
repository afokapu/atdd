# URN: test:migrate-projection-authority:describe-migration-runbook:D001-SMOKE-001-migration-runbook
# Acceptance: acc:migrate-projection-authority:D001-SMOKE-001-migration-runbook
# WMBT: wmbt:migrate-projection-authority:D001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:migrate-projection-authority:D001-SMOKE-001-migration-runbook — fails until the migrate-projection-authority wagon implements it (train 0006). Refs #1400.
"""RED skeleton for acc:migrate-projection-authority:D001-SMOKE-001-migration-runbook.

wagon: migrate-projection-authority | feature: describe-migration-runbook | phase: SMOKE
WMBT: wmbt:migrate-projection-authority:D001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the migrate-projection-authority wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.smoke
@pytest.mark.xfail(strict=True, reason="migrate-projection-authority not yet implemented (RED; #1400)")
def test_d001_smoke_001_migration_runbook(tmp_path) -> None:
    """D001-SMOKE-001-migration-runbook — behaviour not yet implemented."""
    raise AssertionError(
        "RED: migrate-projection-authority acceptance acc:migrate-projection-authority:D001-SMOKE-001-migration-runbook is not implemented yet"
    )
