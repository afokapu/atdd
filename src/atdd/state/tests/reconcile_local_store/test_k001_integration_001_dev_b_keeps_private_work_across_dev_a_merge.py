# URN: test:reconcile-local-store:verify-collaboration-flow:K001-INTEGRATION-001-dev-b-keeps-private-work-across-dev-a-merge
# Acceptance: acc:reconcile-local-store:K001-INTEGRATION-001-dev-b-keeps-private-work-across-dev-a-merge
# WMBT: wmbt:reconcile-local-store:K001
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:reconcile-local-store:K001-INTEGRATION-001-dev-b-keeps-private-work-across-dev-a-merge — fails until the reconcile-local-store wagon implements it (train 0006). Refs #1400.
"""RED skeleton for acc:reconcile-local-store:K001-INTEGRATION-001-dev-b-keeps-private-work-across-dev-a-merge.

wagon: reconcile-local-store | feature: verify-collaboration-flow | phase: RED
WMBT: wmbt:reconcile-local-store:K001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the reconcile-local-store wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="reconcile-local-store not yet implemented (RED; #1400)")
def test_k001_integration_001_dev_b_keeps_private_work_across_dev_a_merge(tmp_path) -> None:
    """K001-INTEGRATION-001-dev-b-keeps-private-work-across-dev-a-merge — behaviour not yet implemented."""
    raise AssertionError(
        "RED: reconcile-local-store acceptance acc:reconcile-local-store:K001-INTEGRATION-001-dev-b-keeps-private-work-across-dev-a-merge is not implemented yet"
    )
