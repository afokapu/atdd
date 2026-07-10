# URN: test:project-shared-state:mint-object-identity:E004-UNIT-001-mints-unique-immutable-uid
# Acceptance: acc:project-shared-state:E004-UNIT-001-mints-unique-immutable-uid
# WMBT: wmbt:project-shared-state:E004
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:project-shared-state:E004-UNIT-001-mints-unique-immutable-uid — fails until the project-shared-state wagon implements it (train 0006). Refs #1433.
"""RED skeleton for acc:project-shared-state:E004-UNIT-001-mints-unique-immutable-uid.

wagon: project-shared-state | feature: mint-object-identity | phase: RED
WMBT: wmbt:project-shared-state:E004

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the project-shared-state wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1433 / #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="project-shared-state not yet implemented (RED; #1433)")
def test_e004_unit_001_mints_unique_immutable_uid(tmp_path) -> None:
    """E004-UNIT-001-mints-unique-immutable-uid — behaviour not yet implemented."""
    raise AssertionError(
        "RED: project-shared-state acceptance acc:project-shared-state:E004-UNIT-001-mints-unique-immutable-uid is not implemented yet"
    )
