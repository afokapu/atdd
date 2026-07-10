# URN: test:enforce-merge-authority:run-merge-checks:E002-UNIT-001-workflow-omits-required-checks
# Acceptance: acc:enforce-merge-authority:E002-UNIT-001-workflow-omits-required-checks
# WMBT: wmbt:enforce-merge-authority:E002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:enforce-merge-authority:E002-UNIT-001-workflow-omits-required-checks — fails until the enforce-merge-authority wagon implements it. Refs #1400.
"""RED skeleton for acc:enforce-merge-authority:E002-UNIT-001-workflow-omits-required-checks.

wagon: enforce-merge-authority | feature: run-merge-checks | phase: RED
WMBT: wmbt:enforce-merge-authority:E002

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the enforce-merge-authority wagon lands the behaviour (a merge-authority workflow omitting any section-4 required check is rejected). When it
xpasses, drop the xfail marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest

@pytest.mark.xfail(strict=True, reason="enforce-merge-authority not yet implemented (RED; #1400)")
def test_e002_unit_001_workflow_omits_required_checks() -> None:
    """E002-UNIT-001-workflow-omits-required-checks — behaviour not yet implemented."""
    raise AssertionError(
        "RED: enforce-merge-authority acceptance acc:enforce-merge-authority:E002-UNIT-001-workflow-omits-required-checks is not implemented yet"
    )
