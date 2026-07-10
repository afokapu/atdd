# URN: test:govern-projection-fields:define-field-ownership:D001-UNIT-002-green-policy-declares-writer-and-merge-rule
# Acceptance: acc:govern-projection-fields:D001-UNIT-002-green-policy-declares-writer-and-merge-rule
# WMBT: wmbt:govern-projection-fields:D001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:govern-projection-fields:D001-UNIT-002-green-policy-declares-writer-and-merge-rule — fails until the govern-projection-fields wagon implements it. Refs #1400.
"""RED skeleton for acc:govern-projection-fields:D001-UNIT-002-green-policy-declares-writer-and-merge-rule.

wagon: govern-projection-fields | feature: define-field-ownership | phase: RED
WMBT: wmbt:govern-projection-fields:D001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the govern-projection-fields wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="govern-projection-fields not yet implemented (RED; #1400)")
def test_d001_unit_002_green_policy_declares_writer_and_merge_rule() -> None:
    """D001-UNIT-002-green-policy-declares-writer-and-merge-rule — behaviour not yet implemented."""
    raise AssertionError(
        "RED: govern-projection-fields acceptance acc:govern-projection-fields:D001-UNIT-002-green-policy-declares-writer-and-merge-rule is not implemented yet"
    )
