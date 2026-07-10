# URN: test:govern-projection-fields:validate-field-writer:E001-UNIT-001-red-human-writes-external-refs
# Acceptance: acc:govern-projection-fields:E001-UNIT-001-red-human-writes-external-refs
# WMBT: wmbt:govern-projection-fields:E001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:govern-projection-fields:E001-UNIT-001-red-human-writes-external-refs — fails until the govern-projection-fields wagon implements it. Refs #1400.
"""RED skeleton for acc:govern-projection-fields:E001-UNIT-001-red-human-writes-external-refs.

wagon: govern-projection-fields | feature: validate-field-writer | phase: RED
WMBT: wmbt:govern-projection-fields:E001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the govern-projection-fields wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="govern-projection-fields not yet implemented (RED; #1400)")
def test_e001_unit_001_red_human_writes_external_refs() -> None:
    """E001-UNIT-001-red-human-writes-external-refs — behaviour not yet implemented."""
    raise AssertionError(
        "RED: govern-projection-fields acceptance acc:govern-projection-fields:E001-UNIT-001-red-human-writes-external-refs is not implemented yet"
    )
