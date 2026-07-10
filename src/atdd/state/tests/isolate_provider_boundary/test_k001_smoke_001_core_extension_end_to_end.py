# URN: test:isolate-provider-boundary:validate-extension-integration:K001-SMOKE-001-core-extension-end-to-end
# Acceptance: acc:isolate-provider-boundary:K001-SMOKE-001-core-extension-end-to-end
# WMBT: wmbt:isolate-provider-boundary:K001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:isolate-provider-boundary:K001-SMOKE-001-core-extension-end-to-end — fails until the isolate-provider-boundary wagon implements it. Refs #1400.
"""RED skeleton for acc:isolate-provider-boundary:K001-SMOKE-001-core-extension-end-to-end.

wagon: isolate-provider-boundary | feature: validate-extension-integration | phase: SMOKE
WMBT: wmbt:isolate-provider-boundary:K001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the isolate-provider-boundary wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.smoke
@pytest.mark.xfail(strict=True, reason="isolate-provider-boundary not yet implemented (RED; #1400)")
def test_k001_smoke_001_core_extension_end_to_end(tmp_path) -> None:
    """K001-SMOKE-001-core-extension-end-to-end — behaviour not yet implemented."""
    raise AssertionError(
        "RED: isolate-provider-boundary acceptance acc:isolate-provider-boundary:K001-SMOKE-001-core-extension-end-to-end is not implemented yet"
    )
