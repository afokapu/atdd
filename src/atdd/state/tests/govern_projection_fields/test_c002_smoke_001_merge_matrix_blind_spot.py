# URN: test:govern-projection-fields:verify-merge-matrix:C002-SMOKE-001-merge-matrix-blind-spot
# Acceptance: acc:govern-projection-fields:C002-SMOKE-001-merge-matrix-blind-spot
# WMBT: wmbt:govern-projection-fields:C002
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:govern-projection-fields:C002-SMOKE-001-merge-matrix-blind-spot — fails until the govern-projection-fields wagon implements it. Refs #1400.
"""RED skeleton for acc:govern-projection-fields:C002-SMOKE-001-merge-matrix-blind-spot.

wagon: govern-projection-fields | feature: verify-merge-matrix | phase: SMOKE
WMBT: wmbt:govern-projection-fields:C002

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the govern-projection-fields wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.smoke
@pytest.mark.xfail(strict=True, reason="govern-projection-fields not yet implemented (RED; #1400)")
def test_c002_smoke_001_merge_matrix_blind_spot(tmp_path) -> None:
    """C002-SMOKE-001-merge-matrix-blind-spot — behaviour not yet implemented."""
    raise AssertionError(
        "RED: govern-projection-fields acceptance acc:govern-projection-fields:C002-SMOKE-001-merge-matrix-blind-spot is not implemented yet"
    )
