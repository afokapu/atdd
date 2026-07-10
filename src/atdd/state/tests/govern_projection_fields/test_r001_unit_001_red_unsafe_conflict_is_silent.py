# URN: test:govern-projection-fields:merge-projection-objects:R001-UNIT-001-red-unsafe-conflict-is-silent
# Acceptance: acc:govern-projection-fields:R001-UNIT-001-red-unsafe-conflict-is-silent
# WMBT: wmbt:govern-projection-fields:R001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:govern-projection-fields:R001-UNIT-001-red-unsafe-conflict-is-silent — fails until the govern-projection-fields wagon implements it. Refs #1400.
"""RED skeleton for acc:govern-projection-fields:R001-UNIT-001-red-unsafe-conflict-is-silent.

wagon: govern-projection-fields | feature: merge-projection-objects | phase: RED
WMBT: wmbt:govern-projection-fields:R001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the govern-projection-fields wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="govern-projection-fields not yet implemented (RED; #1400)")
def test_r001_unit_001_red_unsafe_conflict_is_silent() -> None:
    """R001-UNIT-001-red-unsafe-conflict-is-silent — behaviour not yet implemented."""
    raise AssertionError(
        "RED: govern-projection-fields acceptance acc:govern-projection-fields:R001-UNIT-001-red-unsafe-conflict-is-silent is not implemented yet"
    )
