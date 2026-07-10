# URN: test:govern-projection-fields:define-field-ownership:D001-SMOKE-001-field-ownership-policy
# Acceptance: acc:govern-projection-fields:D001-SMOKE-001-field-ownership-policy
# WMBT: wmbt:govern-projection-fields:D001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:govern-projection-fields:D001-SMOKE-001-field-ownership-policy — fails until the govern-projection-fields wagon implements it. Refs #1400.
"""RED skeleton for acc:govern-projection-fields:D001-SMOKE-001-field-ownership-policy.

wagon: govern-projection-fields | feature: define-field-ownership | phase: SMOKE
WMBT: wmbt:govern-projection-fields:D001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the govern-projection-fields wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.smoke
@pytest.mark.xfail(strict=True, reason="govern-projection-fields not yet implemented (RED; #1400)")
def test_d001_smoke_001_field_ownership_policy(tmp_path) -> None:
    """D001-SMOKE-001-field-ownership-policy — behaviour not yet implemented."""
    raise AssertionError(
        "RED: govern-projection-fields acceptance acc:govern-projection-fields:D001-SMOKE-001-field-ownership-policy is not implemented yet"
    )
