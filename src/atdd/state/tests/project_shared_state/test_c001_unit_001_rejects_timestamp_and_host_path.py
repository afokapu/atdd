# URN: test:project-shared-state:project-store:C001-UNIT-001-rejects-timestamp-and-host-path
# Acceptance: acc:project-shared-state:C001-UNIT-001-rejects-timestamp-and-host-path
# WMBT: wmbt:project-shared-state:C001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:project-shared-state:C001-UNIT-001-rejects-timestamp-and-host-path — fails until the project-shared-state wagon implements it (train 0006). Refs #1433.
"""RED skeleton for acc:project-shared-state:C001-UNIT-001-rejects-timestamp-and-host-path.

wagon: project-shared-state | feature: project-store | phase: RED
WMBT: wmbt:project-shared-state:C001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the project-shared-state wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1433 / #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="project-shared-state not yet implemented (RED; #1433)")
def test_c001_unit_001_rejects_timestamp_and_host_path(tmp_path) -> None:
    """C001-UNIT-001-rejects-timestamp-and-host-path — behaviour not yet implemented."""
    raise AssertionError(
        "RED: project-shared-state acceptance acc:project-shared-state:C001-UNIT-001-rejects-timestamp-and-host-path is not implemented yet"
    )
