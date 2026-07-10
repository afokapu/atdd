# URN: test:govern-projection-fields:define-field-ownership:C001-UNIT-002-green-rejects-gap-and-unknown-writer
# Acceptance: acc:govern-projection-fields:C001-UNIT-002-green-rejects-gap-and-unknown-writer
# WMBT: wmbt:govern-projection-fields:C001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:govern-projection-fields:C001-UNIT-002-green-rejects-gap-and-unknown-writer — fails until the govern-projection-fields wagon implements it. Refs #1400.
"""RED skeleton for acc:govern-projection-fields:C001-UNIT-002-green-rejects-gap-and-unknown-writer.

wagon: govern-projection-fields | feature: define-field-ownership | phase: RED
WMBT: wmbt:govern-projection-fields:C001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the govern-projection-fields wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="govern-projection-fields not yet implemented (RED; #1400)")
def test_c001_unit_002_green_rejects_gap_and_unknown_writer() -> None:
    """C001-UNIT-002-green-rejects-gap-and-unknown-writer — behaviour not yet implemented."""
    raise AssertionError(
        "RED: govern-projection-fields acceptance acc:govern-projection-fields:C001-UNIT-002-green-rejects-gap-and-unknown-writer is not implemented yet"
    )
