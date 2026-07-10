# URN: test:migrate-projection-authority:migrate-manifest-projection:C001-SMOKE-001-lossy-migration-write
# Acceptance: acc:migrate-projection-authority:C001-SMOKE-001-lossy-migration-write
# WMBT: wmbt:migrate-projection-authority:C001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:migrate-projection-authority:C001-SMOKE-001-lossy-migration-write — fails until the migrate-projection-authority wagon implements it (train 0006). Refs #1400.
"""RED skeleton for acc:migrate-projection-authority:C001-SMOKE-001-lossy-migration-write.

wagon: migrate-projection-authority | feature: migrate-manifest-projection | phase: SMOKE
WMBT: wmbt:migrate-projection-authority:C001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the migrate-projection-authority wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.smoke
@pytest.mark.xfail(strict=True, reason="migrate-projection-authority not yet implemented (RED; #1400)")
def test_c001_smoke_001_lossy_migration_write(tmp_path) -> None:
    """C001-SMOKE-001-lossy-migration-write — behaviour not yet implemented."""
    raise AssertionError(
        "RED: migrate-projection-authority acceptance acc:migrate-projection-authority:C001-SMOKE-001-lossy-migration-write is not implemented yet"
    )
