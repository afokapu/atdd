# URN: test:reconcile-local-store:verify-collaboration-flow:K001-INTEGRATION-002-same-object-divergence-conflicts-by-design
# Acceptance: acc:reconcile-local-store:K001-INTEGRATION-002-same-object-divergence-conflicts-by-design
# WMBT: wmbt:reconcile-local-store:K001
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:reconcile-local-store:K001-INTEGRATION-002-same-object-divergence-conflicts-by-design — fails until the reconcile-local-store wagon implements it (train 0006). Refs #1400.
"""RED skeleton for acc:reconcile-local-store:K001-INTEGRATION-002-same-object-divergence-conflicts-by-design.

wagon: reconcile-local-store | feature: verify-collaboration-flow | phase: RED
WMBT: wmbt:reconcile-local-store:K001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the reconcile-local-store wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="reconcile-local-store not yet implemented (RED; #1400)")
def test_k001_integration_002_same_object_divergence_conflicts_by_design(tmp_path) -> None:
    """K001-INTEGRATION-002-same-object-divergence-conflicts-by-design — behaviour not yet implemented."""
    raise AssertionError(
        "RED: reconcile-local-store acceptance acc:reconcile-local-store:K001-INTEGRATION-002-same-object-divergence-conflicts-by-design is not implemented yet"
    )
