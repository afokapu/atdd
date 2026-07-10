# URN: test:isolate-provider-boundary:verify-remote-conformance:C002-INTEGRATION-002-bare-remote-workflow-passes
# Acceptance: acc:isolate-provider-boundary:C002-INTEGRATION-002-bare-remote-workflow-passes
# WMBT: wmbt:isolate-provider-boundary:C002
# Phase: GREEN
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:isolate-provider-boundary:C002-INTEGRATION-002-bare-remote-workflow-passes — fails until the isolate-provider-boundary wagon implements it. Refs #1400.
"""RED skeleton for acc:isolate-provider-boundary:C002-INTEGRATION-002-bare-remote-workflow-passes.

wagon: isolate-provider-boundary | feature: verify-remote-conformance | phase: GREEN
WMBT: wmbt:isolate-provider-boundary:C002

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the isolate-provider-boundary wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="isolate-provider-boundary not yet implemented (RED; #1400)")
def test_c002_integration_002_bare_remote_workflow_passes(tmp_path) -> None:
    """C002-INTEGRATION-002-bare-remote-workflow-passes — behaviour not yet implemented."""
    raise AssertionError(
        "RED: isolate-provider-boundary acceptance acc:isolate-provider-boundary:C002-INTEGRATION-002-bare-remote-workflow-passes is not implemented yet"
    )
