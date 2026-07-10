# URN: test:isolate-provider-boundary:validate-extension-integration:K001-INTEGRATION-001-provider-failure-never-blocks-merge
# Acceptance: acc:isolate-provider-boundary:K001-INTEGRATION-001-provider-failure-never-blocks-merge
# WMBT: wmbt:isolate-provider-boundary:K001
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:isolate-provider-boundary:K001-INTEGRATION-001-provider-failure-never-blocks-merge — fails until the isolate-provider-boundary wagon implements it. Refs #1400.
"""RED skeleton for acc:isolate-provider-boundary:K001-INTEGRATION-001-provider-failure-never-blocks-merge.

wagon: isolate-provider-boundary | feature: validate-extension-integration | phase: RED
WMBT: wmbt:isolate-provider-boundary:K001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the isolate-provider-boundary wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="isolate-provider-boundary not yet implemented (RED; #1400)")
def test_k001_integration_001_provider_failure_never_blocks_merge(tmp_path) -> None:
    """K001-INTEGRATION-001-provider-failure-never-blocks-merge — behaviour not yet implemented."""
    raise AssertionError(
        "RED: isolate-provider-boundary acceptance acc:isolate-provider-boundary:K001-INTEGRATION-001-provider-failure-never-blocks-merge is not implemented yet"
    )
