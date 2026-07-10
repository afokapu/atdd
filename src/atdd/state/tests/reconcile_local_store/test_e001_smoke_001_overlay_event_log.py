# URN: test:reconcile-local-store:record-overlay-events:E001-SMOKE-001-overlay-event-log
# Acceptance: acc:reconcile-local-store:E001-SMOKE-001-overlay-event-log
# WMBT: wmbt:reconcile-local-store:E001
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:reconcile-local-store:E001-SMOKE-001-overlay-event-log — fails until the reconcile-local-store wagon implements it (train 0006). Refs #1400.
"""RED skeleton for acc:reconcile-local-store:E001-SMOKE-001-overlay-event-log.

wagon: reconcile-local-store | feature: record-overlay-events | phase: RED
WMBT: wmbt:reconcile-local-store:E001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the reconcile-local-store wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.smoke
@pytest.mark.xfail(strict=True, reason="reconcile-local-store not yet implemented (RED; #1400)")
def test_e001_smoke_001_overlay_event_log(tmp_path) -> None:
    """E001-SMOKE-001-overlay-event-log — behaviour not yet implemented."""
    raise AssertionError(
        "RED: reconcile-local-store acceptance acc:reconcile-local-store:E001-SMOKE-001-overlay-event-log is not implemented yet"
    )
