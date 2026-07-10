# URN: test:govern-projection-fields:define-actor-ownership:D002-SMOKE-001-single-owner-body-rule-computability
# Acceptance: acc:govern-projection-fields:D002-SMOKE-001-single-owner-body-rule-computability
# WMBT: wmbt:govern-projection-fields:D002
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:govern-projection-fields:D002-SMOKE-001-single-owner-body-rule-computability — fails until the govern-projection-fields wagon implements it. Refs #1400.
"""RED skeleton for acc:govern-projection-fields:D002-SMOKE-001-single-owner-body-rule-computability.

wagon: govern-projection-fields | feature: define-actor-ownership | phase: SMOKE
WMBT: wmbt:govern-projection-fields:D002

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the govern-projection-fields wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.smoke
@pytest.mark.xfail(strict=True, reason="govern-projection-fields not yet implemented (RED; #1400)")
def test_d002_smoke_001_single_owner_body_rule_computability(tmp_path) -> None:
    """D002-SMOKE-001-single-owner-body-rule-computability — behaviour not yet implemented."""
    raise AssertionError(
        "RED: govern-projection-fields acceptance acc:govern-projection-fields:D002-SMOKE-001-single-owner-body-rule-computability is not implemented yet"
    )
