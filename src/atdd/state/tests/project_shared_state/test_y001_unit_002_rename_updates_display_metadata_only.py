# URN: test:project-shared-state:mint-object-identity:Y001-UNIT-002-rename-updates-display-metadata-only
# Acceptance: acc:project-shared-state:Y001-UNIT-002-rename-updates-display-metadata-only
# WMBT: wmbt:project-shared-state:Y001
# Phase: GREEN
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:project-shared-state:Y001-UNIT-002-rename-updates-display-metadata-only — fails until the project-shared-state wagon implements it (train 0006). Refs #1433.
"""RED skeleton for acc:project-shared-state:Y001-UNIT-002-rename-updates-display-metadata-only.

wagon: project-shared-state | feature: mint-object-identity | phase: GREEN
WMBT: wmbt:project-shared-state:Y001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the project-shared-state wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1433 / #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="project-shared-state not yet implemented (RED; #1433)")
def test_y001_unit_002_rename_updates_display_metadata_only(tmp_path) -> None:
    """Y001-UNIT-002-rename-updates-display-metadata-only — behaviour not yet implemented."""
    raise AssertionError(
        "RED: project-shared-state acceptance acc:project-shared-state:Y001-UNIT-002-rename-updates-display-metadata-only is not implemented yet"
    )
