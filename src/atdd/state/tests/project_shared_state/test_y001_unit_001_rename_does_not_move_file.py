# URN: test:project-shared-state:mint-object-identity:Y001-UNIT-001-rename-does-not-move-file
# Acceptance: acc:project-shared-state:Y001-UNIT-001-rename-does-not-move-file
# WMBT: wmbt:project-shared-state:Y001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:project-shared-state:Y001-UNIT-001-rename-does-not-move-file — fails until the project-shared-state wagon implements it (train 0006). Refs #1433.
"""RED skeleton for acc:project-shared-state:Y001-UNIT-001-rename-does-not-move-file.

wagon: project-shared-state | feature: mint-object-identity | phase: RED
WMBT: wmbt:project-shared-state:Y001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the project-shared-state wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1433 / #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="project-shared-state not yet implemented (RED; #1433)")
def test_y001_unit_001_rename_does_not_move_file(tmp_path) -> None:
    """Y001-UNIT-001-rename-does-not-move-file — behaviour not yet implemented."""
    raise AssertionError(
        "RED: project-shared-state acceptance acc:project-shared-state:Y001-UNIT-001-rename-does-not-move-file is not implemented yet"
    )
