# URN: test:isolate-provider-boundary:lock-extension-digests:E002-UNIT-001-rejects-lock-missing-digest
# Acceptance: acc:isolate-provider-boundary:E002-UNIT-001-rejects-lock-missing-digest
# WMBT: wmbt:isolate-provider-boundary:E002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:isolate-provider-boundary:E002-UNIT-001-rejects-lock-missing-digest — fails until the isolate-provider-boundary wagon implements it. Refs #1400.
"""RED skeleton for acc:isolate-provider-boundary:E002-UNIT-001-rejects-lock-missing-digest.

wagon: isolate-provider-boundary | feature: lock-extension-digests | phase: RED
WMBT: wmbt:isolate-provider-boundary:E002

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the isolate-provider-boundary wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="isolate-provider-boundary not yet implemented (RED; #1400)")
def test_e002_unit_001_rejects_lock_missing_digest(tmp_path) -> None:
    """E002-UNIT-001-rejects-lock-missing-digest — behaviour not yet implemented."""
    raise AssertionError(
        "RED: isolate-provider-boundary acceptance acc:isolate-provider-boundary:E002-UNIT-001-rejects-lock-missing-digest is not implemented yet"
    )
