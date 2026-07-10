# URN: test:reconcile-local-store:reconcile-store-state:R001-UNIT-002-invalid-replay-does-not-advance-base
# Acceptance: acc:reconcile-local-store:R001-UNIT-002-invalid-replay-does-not-advance-base
# WMBT: wmbt:reconcile-local-store:R001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:reconcile-local-store:R001-UNIT-002-invalid-replay-does-not-advance-base — fails until the reconcile-local-store wagon implements it (train 0006). Refs #1400.
"""RED skeleton for acc:reconcile-local-store:R001-UNIT-002-invalid-replay-does-not-advance-base.

wagon: reconcile-local-store | feature: reconcile-store-state | phase: RED
WMBT: wmbt:reconcile-local-store:R001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the reconcile-local-store wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="reconcile-local-store not yet implemented (RED; #1400)")
def test_r001_unit_002_invalid_replay_does_not_advance_base(tmp_path) -> None:
    """R001-UNIT-002-invalid-replay-does-not-advance-base — behaviour not yet implemented."""
    raise AssertionError(
        "RED: reconcile-local-store acceptance acc:reconcile-local-store:R001-UNIT-002-invalid-replay-does-not-advance-base is not implemented yet"
    )
