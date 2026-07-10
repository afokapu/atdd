# URN: test:govern-projection-fields:define-field-ownership:C001-SMOKE-001-policy-coverage-gap
# Acceptance: acc:govern-projection-fields:C001-SMOKE-001-policy-coverage-gap
# WMBT: wmbt:govern-projection-fields:C001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:govern-projection-fields:C001-SMOKE-001-policy-coverage-gap — fails until the govern-projection-fields wagon implements it. Refs #1400.
"""RED skeleton for acc:govern-projection-fields:C001-SMOKE-001-policy-coverage-gap.

wagon: govern-projection-fields | feature: define-field-ownership | phase: SMOKE
WMBT: wmbt:govern-projection-fields:C001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the govern-projection-fields wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.smoke
@pytest.mark.xfail(strict=True, reason="govern-projection-fields not yet implemented (RED; #1400)")
def test_c001_smoke_001_policy_coverage_gap(tmp_path) -> None:
    """C001-SMOKE-001-policy-coverage-gap — behaviour not yet implemented."""
    raise AssertionError(
        "RED: govern-projection-fields acceptance acc:govern-projection-fields:C001-SMOKE-001-policy-coverage-gap is not implemented yet"
    )
