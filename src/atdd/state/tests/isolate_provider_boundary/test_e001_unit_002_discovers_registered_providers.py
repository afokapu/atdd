# URN: test:isolate-provider-boundary:register-sync-providers:E001-UNIT-002-discovers-registered-providers
# Acceptance: acc:isolate-provider-boundary:E001-UNIT-002-discovers-registered-providers
# WMBT: wmbt:isolate-provider-boundary:E001
# Phase: GREEN
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:isolate-provider-boundary:E001-UNIT-002-discovers-registered-providers — fails until the isolate-provider-boundary wagon implements it. Refs #1400.
"""RED skeleton for acc:isolate-provider-boundary:E001-UNIT-002-discovers-registered-providers.

wagon: isolate-provider-boundary | feature: register-sync-providers | phase: GREEN
WMBT: wmbt:isolate-provider-boundary:E001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the isolate-provider-boundary wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="isolate-provider-boundary not yet implemented (RED; #1400)")
def test_e001_unit_002_discovers_registered_providers(tmp_path) -> None:
    """E001-UNIT-002-discovers-registered-providers — behaviour not yet implemented."""
    raise AssertionError(
        "RED: isolate-provider-boundary acceptance acc:isolate-provider-boundary:E001-UNIT-002-discovers-registered-providers is not implemented yet"
    )
