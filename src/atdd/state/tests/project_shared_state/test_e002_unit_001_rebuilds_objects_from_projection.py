# URN: test:project-shared-state:hydrate-projection:E002-UNIT-001-rebuilds-objects-from-projection
# Acceptance: acc:project-shared-state:E002-UNIT-001-rebuilds-objects-from-projection
# WMBT: wmbt:project-shared-state:E002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:project-shared-state:E002-UNIT-001-rebuilds-objects-from-projection — fails until the project-shared-state wagon implements it (train 0006). Refs #1433.
"""RED skeleton for acc:project-shared-state:E002-UNIT-001-rebuilds-objects-from-projection.

wagon: project-shared-state | feature: hydrate-projection | phase: RED
WMBT: wmbt:project-shared-state:E002

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the project-shared-state wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1433 / #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="project-shared-state not yet implemented (RED; #1433)")
def test_e002_unit_001_rebuilds_objects_from_projection(tmp_path) -> None:
    """E002-UNIT-001-rebuilds-objects-from-projection — behaviour not yet implemented."""
    raise AssertionError(
        "RED: project-shared-state acceptance acc:project-shared-state:E002-UNIT-001-rebuilds-objects-from-projection is not implemented yet"
    )
