# URN: test:reconcile-local-store:reconcile-store-state:R002-UNIT-001-conflict-report-names-events-and-backup
# Acceptance: acc:reconcile-local-store:R002-UNIT-001-conflict-report-names-events-and-backup
# WMBT: wmbt:reconcile-local-store:R002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:reconcile-local-store:R002-UNIT-001-conflict-report-names-events-and-backup — fails until the reconcile-local-store wagon implements it (train 0006). Refs #1400.
"""RED skeleton for acc:reconcile-local-store:R002-UNIT-001-conflict-report-names-events-and-backup.

wagon: reconcile-local-store | feature: reconcile-store-state | phase: RED
WMBT: wmbt:reconcile-local-store:R002

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the reconcile-local-store wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="reconcile-local-store not yet implemented (RED; #1400)")
def test_r002_unit_001_conflict_report_names_events_and_backup(tmp_path) -> None:
    """R002-UNIT-001-conflict-report-names-events-and-backup — behaviour not yet implemented."""
    raise AssertionError(
        "RED: reconcile-local-store acceptance acc:reconcile-local-store:R002-UNIT-001-conflict-report-names-events-and-backup is not implemented yet"
    )
