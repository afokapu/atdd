# URN: test:govern-projection-fields:merge-projection-objects:E002-UNIT-002-green-auto-merges-the-three-safe-cases
# Acceptance: acc:govern-projection-fields:E002-UNIT-002-green-auto-merges-the-three-safe-cases
# WMBT: wmbt:govern-projection-fields:E002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:govern-projection-fields:E002-UNIT-002-green-auto-merges-the-three-safe-cases — fails until the govern-projection-fields wagon implements it. Refs #1400.
"""RED skeleton for acc:govern-projection-fields:E002-UNIT-002-green-auto-merges-the-three-safe-cases.

wagon: govern-projection-fields | feature: merge-projection-objects | phase: RED
WMBT: wmbt:govern-projection-fields:E002

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the govern-projection-fields wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="govern-projection-fields not yet implemented (RED; #1400)")
def test_e002_unit_002_green_auto_merges_the_three_safe_cases() -> None:
    """E002-UNIT-002-green-auto-merges-the-three-safe-cases — behaviour not yet implemented."""
    raise AssertionError(
        "RED: govern-projection-fields acceptance acc:govern-projection-fields:E002-UNIT-002-green-auto-merges-the-three-safe-cases is not implemented yet"
    )
