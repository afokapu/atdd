# URN: test:project-shared-state:project-store:E001-UNIT-001-same-store-yields-identical-bytes
# Acceptance: acc:project-shared-state:E001-UNIT-001-same-store-yields-identical-bytes
# WMBT: wmbt:project-shared-state:E001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:project-shared-state:E001-UNIT-001-same-store-yields-identical-bytes — fails until the project-shared-state wagon implements it (train 0006). Refs #1433.
"""RED skeleton for acc:project-shared-state:E001-UNIT-001-same-store-yields-identical-bytes.

wagon: project-shared-state | feature: project-store | phase: RED
WMBT: wmbt:project-shared-state:E001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the project-shared-state wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1433 / #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="project-shared-state not yet implemented (RED; #1433)")
def test_e001_unit_001_same_store_yields_identical_bytes(tmp_path) -> None:
    """E001-UNIT-001-same-store-yields-identical-bytes — behaviour not yet implemented."""
    raise AssertionError(
        "RED: project-shared-state acceptance acc:project-shared-state:E001-UNIT-001-same-store-yields-identical-bytes is not implemented yet"
    )
