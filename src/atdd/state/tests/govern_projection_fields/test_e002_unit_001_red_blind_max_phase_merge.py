# URN: test:govern-projection-fields:merge-projection-objects:E002-UNIT-001-red-blind-max-phase-merge
# Acceptance: acc:govern-projection-fields:E002-UNIT-001-red-blind-max-phase-merge
# WMBT: wmbt:govern-projection-fields:E002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:govern-projection-fields:E002-UNIT-001-red-blind-max-phase-merge — fails until the govern-projection-fields wagon implements it. Refs #1400.
"""RED skeleton for acc:govern-projection-fields:E002-UNIT-001-red-blind-max-phase-merge.

wagon: govern-projection-fields | feature: merge-projection-objects | phase: RED
WMBT: wmbt:govern-projection-fields:E002

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the govern-projection-fields wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="govern-projection-fields not yet implemented (RED; #1400)")
def test_e002_unit_001_red_blind_max_phase_merge() -> None:
    """E002-UNIT-001-red-blind-max-phase-merge — behaviour not yet implemented."""
    raise AssertionError(
        "RED: govern-projection-fields acceptance acc:govern-projection-fields:E002-UNIT-001-red-blind-max-phase-merge is not implemented yet"
    )
