# URN: test:isolate-provider-boundary:verify-remote-conformance:C002-INTEGRATION-001-fails-when-lifecycle-reads-provider
# Acceptance: acc:isolate-provider-boundary:C002-INTEGRATION-001-fails-when-lifecycle-reads-provider
# WMBT: wmbt:isolate-provider-boundary:C002
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:isolate-provider-boundary:C002-INTEGRATION-001-fails-when-lifecycle-reads-provider — fails until the isolate-provider-boundary wagon implements it. Refs #1400.
"""RED skeleton for acc:isolate-provider-boundary:C002-INTEGRATION-001-fails-when-lifecycle-reads-provider.

wagon: isolate-provider-boundary | feature: verify-remote-conformance | phase: RED
WMBT: wmbt:isolate-provider-boundary:C002

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the isolate-provider-boundary wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="isolate-provider-boundary not yet implemented (RED; #1400)")
def test_c002_integration_001_fails_when_lifecycle_reads_provider(tmp_path) -> None:
    """C002-INTEGRATION-001-fails-when-lifecycle-reads-provider — behaviour not yet implemented."""
    raise AssertionError(
        "RED: isolate-provider-boundary acceptance acc:isolate-provider-boundary:C002-INTEGRATION-001-fails-when-lifecycle-reads-provider is not implemented yet"
    )
