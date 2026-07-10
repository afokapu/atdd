# URN: test:reconcile-local-store:trigger-head-hooks:M001-UNIT-002-bypassed-hook-leaves-detectable-stale-base
# Acceptance: acc:reconcile-local-store:M001-UNIT-002-bypassed-hook-leaves-detectable-stale-base
# WMBT: wmbt:reconcile-local-store:M001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:reconcile-local-store:M001-UNIT-002-bypassed-hook-leaves-detectable-stale-base — fails until the reconcile-local-store wagon implements it (train 0006). Refs #1400.
"""RED skeleton for acc:reconcile-local-store:M001-UNIT-002-bypassed-hook-leaves-detectable-stale-base.

wagon: reconcile-local-store | feature: trigger-head-hooks | phase: RED
WMBT: wmbt:reconcile-local-store:M001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the reconcile-local-store wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="reconcile-local-store not yet implemented (RED; #1400)")
def test_m001_unit_002_bypassed_hook_leaves_detectable_stale_base(tmp_path) -> None:
    """M001-UNIT-002-bypassed-hook-leaves-detectable-stale-base — behaviour not yet implemented."""
    raise AssertionError(
        "RED: reconcile-local-store acceptance acc:reconcile-local-store:M001-UNIT-002-bypassed-hook-leaves-detectable-stale-base is not implemented yet"
    )
