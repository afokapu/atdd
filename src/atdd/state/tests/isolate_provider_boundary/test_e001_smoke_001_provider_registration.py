# URN: test:isolate-provider-boundary:register-sync-providers:E001-SMOKE-001-provider-registration
# Acceptance: acc:isolate-provider-boundary:E001-SMOKE-001-provider-registration
# WMBT: wmbt:isolate-provider-boundary:E001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:isolate-provider-boundary:E001-SMOKE-001-provider-registration — fails until the isolate-provider-boundary wagon implements it. Refs #1400.
"""RED skeleton for acc:isolate-provider-boundary:E001-SMOKE-001-provider-registration.

wagon: isolate-provider-boundary | feature: register-sync-providers | phase: SMOKE
WMBT: wmbt:isolate-provider-boundary:E001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the isolate-provider-boundary wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.smoke
@pytest.mark.xfail(strict=True, reason="isolate-provider-boundary not yet implemented (RED; #1400)")
def test_e001_smoke_001_provider_registration(tmp_path) -> None:
    """E001-SMOKE-001-provider-registration — behaviour not yet implemented."""
    raise AssertionError(
        "RED: isolate-provider-boundary acceptance acc:isolate-provider-boundary:E001-SMOKE-001-provider-registration is not implemented yet"
    )
