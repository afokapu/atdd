# URN: test:reconcile-local-store:reconcile-store-state:R002-UNIT-002-conflict-keeps-backup-and-store-unchanged
# Acceptance: acc:reconcile-local-store:R002-UNIT-002-conflict-keeps-backup-and-store-unchanged
# WMBT: wmbt:reconcile-local-store:R002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:reconcile-local-store:R002-UNIT-002-conflict-keeps-backup-and-store-unchanged — fails until the reconcile-local-store wagon implements it (train 0006). Refs #1400.
"""RED skeleton for acc:reconcile-local-store:R002-UNIT-002-conflict-keeps-backup-and-store-unchanged.

wagon: reconcile-local-store | feature: reconcile-store-state | phase: RED
WMBT: wmbt:reconcile-local-store:R002

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the reconcile-local-store wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="reconcile-local-store not yet implemented (RED; #1400)")
def test_r002_unit_002_conflict_keeps_backup_and_store_unchanged(tmp_path) -> None:
    """R002-UNIT-002-conflict-keeps-backup-and-store-unchanged — behaviour not yet implemented."""
    raise AssertionError(
        "RED: reconcile-local-store acceptance acc:reconcile-local-store:R002-UNIT-002-conflict-keeps-backup-and-store-unchanged is not implemented yet"
    )
