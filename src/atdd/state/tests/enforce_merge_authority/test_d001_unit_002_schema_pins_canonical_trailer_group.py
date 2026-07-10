# URN: test:enforce-merge-authority:parse-commit-trailer:D001-UNIT-002-schema-pins-canonical-trailer-group
# Acceptance: acc:enforce-merge-authority:D001-UNIT-002-schema-pins-canonical-trailer-group
# WMBT: wmbt:enforce-merge-authority:D001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:enforce-merge-authority:D001-UNIT-002-schema-pins-canonical-trailer-group — fails until the enforce-merge-authority wagon implements it. Refs #1400.
"""RED skeleton for acc:enforce-merge-authority:D001-UNIT-002-schema-pins-canonical-trailer-group.

wagon: enforce-merge-authority | feature: parse-commit-trailer | phase: RED
WMBT: wmbt:enforce-merge-authority:D001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the enforce-merge-authority wagon lands the behaviour (the schema pins the canonical ATDD trailer group, each value grammar, and per-diff-class requirements). When it
xpasses, drop the xfail marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest

@pytest.mark.xfail(strict=True, reason="enforce-merge-authority not yet implemented (RED; #1400)")
def test_d001_unit_002_schema_pins_canonical_trailer_group() -> None:
    """D001-UNIT-002-schema-pins-canonical-trailer-group — behaviour not yet implemented."""
    raise AssertionError(
        "RED: enforce-merge-authority acceptance acc:enforce-merge-authority:D001-UNIT-002-schema-pins-canonical-trailer-group is not implemented yet"
    )
