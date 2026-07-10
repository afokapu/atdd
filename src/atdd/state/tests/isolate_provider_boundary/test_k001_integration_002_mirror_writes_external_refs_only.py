# URN: test:isolate-provider-boundary:validate-extension-integration:K001-INTEGRATION-002-mirror-writes-external-refs-only
# Acceptance: acc:isolate-provider-boundary:K001-INTEGRATION-002-mirror-writes-external-refs-only
# WMBT: wmbt:isolate-provider-boundary:K001
# Phase: GREEN
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:isolate-provider-boundary:K001-INTEGRATION-002-mirror-writes-external-refs-only — fails until the isolate-provider-boundary wagon implements it. Refs #1400.
"""RED skeleton for acc:isolate-provider-boundary:K001-INTEGRATION-002-mirror-writes-external-refs-only.

wagon: isolate-provider-boundary | feature: validate-extension-integration | phase: GREEN
WMBT: wmbt:isolate-provider-boundary:K001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the isolate-provider-boundary wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="isolate-provider-boundary not yet implemented (RED; #1400)")
def test_k001_integration_002_mirror_writes_external_refs_only(tmp_path) -> None:
    """K001-INTEGRATION-002-mirror-writes-external-refs-only — behaviour not yet implemented."""
    raise AssertionError(
        "RED: isolate-provider-boundary acceptance acc:isolate-provider-boundary:K001-INTEGRATION-002-mirror-writes-external-refs-only is not implemented yet"
    )
