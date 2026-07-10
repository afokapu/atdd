# URN: test:enforce-merge-authority:validate-transition-legality:C001-SMOKE-001-illegal-transition-merge
# Acceptance: acc:enforce-merge-authority:C001-SMOKE-001-illegal-transition-merge
# WMBT: wmbt:enforce-merge-authority:C001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:enforce-merge-authority:C001-SMOKE-001-illegal-transition-merge — fails until the enforce-merge-authority wagon implements it. Refs #1400.
"""RED skeleton for acc:enforce-merge-authority:C001-SMOKE-001-illegal-transition-merge.

wagon: enforce-merge-authority | feature: validate-transition-legality | phase: SMOKE
WMBT: wmbt:enforce-merge-authority:C001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the enforce-merge-authority wagon lands the behaviour (illegal-transition-merge holds end-to-end against a real repo, CLI and State Store). When it
xpasses, drop the xfail marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest

@pytest.mark.smoke
@pytest.mark.xfail(strict=True, reason="enforce-merge-authority not yet implemented (RED; #1400)")
def test_c001_smoke_001_illegal_transition_merge(tmp_path) -> None:
    """C001-SMOKE-001-illegal-transition-merge — behaviour not yet implemented."""
    raise AssertionError(
        "RED: enforce-merge-authority acceptance acc:enforce-merge-authority:C001-SMOKE-001-illegal-transition-merge is not implemented yet"
    )
