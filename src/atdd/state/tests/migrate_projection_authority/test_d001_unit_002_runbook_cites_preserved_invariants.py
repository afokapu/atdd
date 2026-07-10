# URN: test:migrate-projection-authority:describe-migration-runbook:D001-UNIT-002-runbook-cites-preserved-invariants
# Acceptance: acc:migrate-projection-authority:D001-UNIT-002-runbook-cites-preserved-invariants
# WMBT: wmbt:migrate-projection-authority:D001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:migrate-projection-authority:D001-UNIT-002-runbook-cites-preserved-invariants — fails until the migrate-projection-authority wagon implements it (train 0006). Refs #1400.
"""RED skeleton for acc:migrate-projection-authority:D001-UNIT-002-runbook-cites-preserved-invariants.

wagon: migrate-projection-authority | feature: describe-migration-runbook | phase: RED
WMBT: wmbt:migrate-projection-authority:D001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the migrate-projection-authority wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="migrate-projection-authority not yet implemented (RED; #1400)")
def test_d001_unit_002_runbook_cites_preserved_invariants(tmp_path) -> None:
    """D001-UNIT-002-runbook-cites-preserved-invariants — behaviour not yet implemented."""
    raise AssertionError(
        "RED: migrate-projection-authority acceptance acc:migrate-projection-authority:D001-UNIT-002-runbook-cites-preserved-invariants is not implemented yet"
    )
