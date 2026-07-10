# URN: test:isolate-provider-boundary:lock-extension-digests:E002-UNIT-002-writes-deterministic-lock
# Acceptance: acc:isolate-provider-boundary:E002-UNIT-002-writes-deterministic-lock
# WMBT: wmbt:isolate-provider-boundary:E002
# Phase: GREEN
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:isolate-provider-boundary:E002-UNIT-002-writes-deterministic-lock — fails until the isolate-provider-boundary wagon implements it. Refs #1400.
"""RED skeleton for acc:isolate-provider-boundary:E002-UNIT-002-writes-deterministic-lock.

wagon: isolate-provider-boundary | feature: lock-extension-digests | phase: GREEN
WMBT: wmbt:isolate-provider-boundary:E002

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the isolate-provider-boundary wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="isolate-provider-boundary not yet implemented (RED; #1400)")
def test_e002_unit_002_writes_deterministic_lock(tmp_path) -> None:
    """E002-UNIT-002-writes-deterministic-lock — behaviour not yet implemented."""
    raise AssertionError(
        "RED: isolate-provider-boundary acceptance acc:isolate-provider-boundary:E002-UNIT-002-writes-deterministic-lock is not implemented yet"
    )
