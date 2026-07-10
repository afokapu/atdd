# URN: test:project-shared-state:verify-projection-canonicality:C002-UNIT-002-roundtrip-identity-holds
# Acceptance: acc:project-shared-state:C002-UNIT-002-roundtrip-identity-holds
# WMBT: wmbt:project-shared-state:C002
# Phase: GREEN
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:project-shared-state:C002-UNIT-002-roundtrip-identity-holds — fails until the project-shared-state wagon implements it (train 0006). Refs #1433.
"""RED skeleton for acc:project-shared-state:C002-UNIT-002-roundtrip-identity-holds.

wagon: project-shared-state | feature: verify-projection-canonicality | phase: GREEN
WMBT: wmbt:project-shared-state:C002

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the project-shared-state wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1433 / #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="project-shared-state not yet implemented (RED; #1433)")
def test_c002_unit_002_roundtrip_identity_holds(tmp_path) -> None:
    """C002-UNIT-002-roundtrip-identity-holds — behaviour not yet implemented."""
    raise AssertionError(
        "RED: project-shared-state acceptance acc:project-shared-state:C002-UNIT-002-roundtrip-identity-holds is not implemented yet"
    )
