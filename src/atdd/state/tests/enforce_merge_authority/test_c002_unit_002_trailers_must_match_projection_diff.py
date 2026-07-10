# URN: test:enforce-merge-authority:verify-trailer-diff:C002-UNIT-002-trailers-must-match-projection-diff
# Acceptance: acc:enforce-merge-authority:C002-UNIT-002-trailers-must-match-projection-diff
# WMBT: wmbt:enforce-merge-authority:C002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:enforce-merge-authority:C002-UNIT-002-trailers-must-match-projection-diff — fails until the enforce-merge-authority wagon implements it. Refs #1400.
"""RED skeleton for acc:enforce-merge-authority:C002-UNIT-002-trailers-must-match-projection-diff.

wagon: enforce-merge-authority | feature: verify-trailer-diff | phase: RED
WMBT: wmbt:enforce-merge-authority:C002

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the enforce-merge-authority wagon lands the behaviour (trailers disagreeing with the projection diff on object, transition or digest are rejected). When it
xpasses, drop the xfail marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest

@pytest.mark.xfail(strict=True, reason="enforce-merge-authority not yet implemented (RED; #1400)")
def test_c002_unit_002_trailers_must_match_projection_diff() -> None:
    """C002-UNIT-002-trailers-must-match-projection-diff — behaviour not yet implemented."""
    raise AssertionError(
        "RED: enforce-merge-authority acceptance acc:enforce-merge-authority:C002-UNIT-002-trailers-must-match-projection-diff is not implemented yet"
    )
