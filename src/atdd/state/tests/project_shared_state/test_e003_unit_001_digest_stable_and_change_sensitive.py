# URN: test:project-shared-state:compute-projection-digest:E003-UNIT-001-digest-stable-and-change-sensitive
# Acceptance: acc:project-shared-state:E003-UNIT-001-digest-stable-and-change-sensitive
# WMBT: wmbt:project-shared-state:E003
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:project-shared-state:E003-UNIT-001-digest-stable-and-change-sensitive — fails until the project-shared-state wagon implements it (train 0006). Refs #1433.
"""RED skeleton for acc:project-shared-state:E003-UNIT-001-digest-stable-and-change-sensitive.

wagon: project-shared-state | feature: compute-projection-digest | phase: RED
WMBT: wmbt:project-shared-state:E003

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the project-shared-state wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1433 / #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="project-shared-state not yet implemented (RED; #1433)")
def test_e003_unit_001_digest_stable_and_change_sensitive(tmp_path) -> None:
    """E003-UNIT-001-digest-stable-and-change-sensitive — behaviour not yet implemented."""
    raise AssertionError(
        "RED: project-shared-state acceptance acc:project-shared-state:E003-UNIT-001-digest-stable-and-change-sensitive is not implemented yet"
    )
