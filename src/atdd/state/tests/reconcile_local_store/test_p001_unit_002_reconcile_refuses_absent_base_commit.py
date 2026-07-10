# URN: test:reconcile-local-store:track-base-commit:P001-UNIT-002-reconcile-refuses-absent-base-commit
# Acceptance: acc:reconcile-local-store:P001-UNIT-002-reconcile-refuses-absent-base-commit
# WMBT: wmbt:reconcile-local-store:P001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:reconcile-local-store:P001-UNIT-002-reconcile-refuses-absent-base-commit — fails until the reconcile-local-store wagon implements it (train 0006). Refs #1400.
"""RED skeleton for acc:reconcile-local-store:P001-UNIT-002-reconcile-refuses-absent-base-commit.

wagon: reconcile-local-store | feature: track-base-commit | phase: RED
WMBT: wmbt:reconcile-local-store:P001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the reconcile-local-store wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="reconcile-local-store not yet implemented (RED; #1400)")
def test_p001_unit_002_reconcile_refuses_absent_base_commit(tmp_path) -> None:
    """P001-UNIT-002-reconcile-refuses-absent-base-commit — behaviour not yet implemented."""
    raise AssertionError(
        "RED: reconcile-local-store acceptance acc:reconcile-local-store:P001-UNIT-002-reconcile-refuses-absent-base-commit is not implemented yet"
    )
