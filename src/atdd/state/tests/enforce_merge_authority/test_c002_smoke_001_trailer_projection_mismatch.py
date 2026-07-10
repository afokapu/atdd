# URN: test:enforce-merge-authority:verify-trailer-diff:C002-SMOKE-001-trailer-projection-mismatch
# Acceptance: acc:enforce-merge-authority:C002-SMOKE-001-trailer-projection-mismatch
# WMBT: wmbt:enforce-merge-authority:C002
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:enforce-merge-authority:C002-SMOKE-001-trailer-projection-mismatch — fails until the enforce-merge-authority wagon implements it. Refs #1400.
"""RED skeleton for acc:enforce-merge-authority:C002-SMOKE-001-trailer-projection-mismatch.

wagon: enforce-merge-authority | feature: verify-trailer-diff | phase: SMOKE
WMBT: wmbt:enforce-merge-authority:C002

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the enforce-merge-authority wagon lands the behaviour (trailer-projection-mismatch holds end-to-end against real infrastructure). When it
xpasses, drop the xfail marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest

@pytest.mark.smoke
@pytest.mark.xfail(strict=True, reason="enforce-merge-authority not yet implemented (RED; #1400)")
def test_c002_smoke_001_trailer_projection_mismatch(tmp_path) -> None:
    """C002-SMOKE-001-trailer-projection-mismatch — behaviour not yet implemented."""
    raise AssertionError(
        "RED: enforce-merge-authority acceptance acc:enforce-merge-authority:C002-SMOKE-001-trailer-projection-mismatch is not implemented yet"
    )
