# URN: test:enforce-merge-authority:validate-transition-legality:C001-UNIT-001-illegal-phase-jump-is-admitted
# Acceptance: acc:enforce-merge-authority:C001-UNIT-001-illegal-phase-jump-is-admitted
# WMBT: wmbt:enforce-merge-authority:C001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:enforce-merge-authority:C001-UNIT-001-illegal-phase-jump-is-admitted — fails until the enforce-merge-authority wagon implements it. Refs #1400.
"""RED skeleton for acc:enforce-merge-authority:C001-UNIT-001-illegal-phase-jump-is-admitted.

wagon: enforce-merge-authority | feature: validate-transition-legality | phase: RED
WMBT: wmbt:enforce-merge-authority:C001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the enforce-merge-authority wagon lands the behaviour (a canonical projection jumping PLANNED->GREEN without RED evidence is rejected by the legal-transition validator). When it
xpasses, drop the xfail marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest

@pytest.mark.xfail(strict=True, reason="enforce-merge-authority not yet implemented (RED; #1400)")
def test_c001_unit_001_illegal_phase_jump_is_admitted() -> None:
    """C001-UNIT-001-illegal-phase-jump-is-admitted — behaviour not yet implemented."""
    raise AssertionError(
        "RED: enforce-merge-authority acceptance acc:enforce-merge-authority:C001-UNIT-001-illegal-phase-jump-is-admitted is not implemented yet"
    )
