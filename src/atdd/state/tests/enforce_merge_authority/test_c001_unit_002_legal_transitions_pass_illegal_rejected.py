# URN: test:enforce-merge-authority:validate-transition-legality:C001-UNIT-002-legal-transitions-pass-illegal-rejected
# Acceptance: acc:enforce-merge-authority:C001-UNIT-002-legal-transitions-pass-illegal-rejected
# WMBT: wmbt:enforce-merge-authority:C001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:enforce-merge-authority:C001-UNIT-002-legal-transitions-pass-illegal-rejected — fails until the enforce-merge-authority wagon implements it. Refs #1400.
"""RED skeleton for acc:enforce-merge-authority:C001-UNIT-002-legal-transitions-pass-illegal-rejected.

wagon: enforce-merge-authority | feature: validate-transition-legality | phase: RED
WMBT: wmbt:enforce-merge-authority:C001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the enforce-merge-authority wagon lands the behaviour (every section-6 legal pair is admitted and backward/skipping/unevidenced transitions are rejected). When it
xpasses, drop the xfail marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest

@pytest.mark.xfail(strict=True, reason="enforce-merge-authority not yet implemented (RED; #1400)")
def test_c001_unit_002_legal_transitions_pass_illegal_rejected() -> None:
    """C001-UNIT-002-legal-transitions-pass-illegal-rejected — behaviour not yet implemented."""
    raise AssertionError(
        "RED: enforce-merge-authority acceptance acc:enforce-merge-authority:C001-UNIT-002-legal-transitions-pass-illegal-rejected is not implemented yet"
    )
