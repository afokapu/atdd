# URN: test:isolate-provider-boundary:define-provider-interface:D001-SMOKE-001-sync-provider-interface
# Acceptance: acc:isolate-provider-boundary:D001-SMOKE-001-sync-provider-interface
# WMBT: wmbt:isolate-provider-boundary:D001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:isolate-provider-boundary:D001-SMOKE-001-sync-provider-interface — fails until the isolate-provider-boundary wagon implements it. Refs #1400.
"""RED skeleton for acc:isolate-provider-boundary:D001-SMOKE-001-sync-provider-interface.

wagon: isolate-provider-boundary | feature: define-provider-interface | phase: SMOKE
WMBT: wmbt:isolate-provider-boundary:D001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the isolate-provider-boundary wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.smoke
@pytest.mark.xfail(strict=True, reason="isolate-provider-boundary not yet implemented (RED; #1400)")
def test_d001_smoke_001_sync_provider_interface(tmp_path) -> None:
    """D001-SMOKE-001-sync-provider-interface — behaviour not yet implemented."""
    raise AssertionError(
        "RED: isolate-provider-boundary acceptance acc:isolate-provider-boundary:D001-SMOKE-001-sync-provider-interface is not implemented yet"
    )
