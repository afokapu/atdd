# URN: test:isolate-provider-boundary:verify-remote-conformance:C002-SMOKE-001-provider-free-workflow
# Acceptance: acc:isolate-provider-boundary:C002-SMOKE-001-provider-free-workflow
# WMBT: wmbt:isolate-provider-boundary:C002
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:isolate-provider-boundary:C002-SMOKE-001-provider-free-workflow — fails until the isolate-provider-boundary wagon implements it. Refs #1400.
"""RED skeleton for acc:isolate-provider-boundary:C002-SMOKE-001-provider-free-workflow.

wagon: isolate-provider-boundary | feature: verify-remote-conformance | phase: SMOKE
WMBT: wmbt:isolate-provider-boundary:C002

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the isolate-provider-boundary wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.smoke
@pytest.mark.xfail(strict=True, reason="isolate-provider-boundary not yet implemented (RED; #1400)")
def test_c002_smoke_001_provider_free_workflow(tmp_path) -> None:
    """C002-SMOKE-001-provider-free-workflow — behaviour not yet implemented."""
    raise AssertionError(
        "RED: isolate-provider-boundary acceptance acc:isolate-provider-boundary:C002-SMOKE-001-provider-free-workflow is not implemented yet"
    )
