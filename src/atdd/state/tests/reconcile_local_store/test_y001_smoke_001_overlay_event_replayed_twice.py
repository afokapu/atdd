# URN: test:reconcile-local-store:archive-overlay-events:Y001-SMOKE-001-overlay-event-replayed-twice
# Acceptance: acc:reconcile-local-store:Y001-SMOKE-001-overlay-event-replayed-twice
# WMBT: wmbt:reconcile-local-store:Y001
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:reconcile-local-store:Y001-SMOKE-001-overlay-event-replayed-twice — fails until the reconcile-local-store wagon implements it (train 0006). Refs #1400.
"""RED skeleton for acc:reconcile-local-store:Y001-SMOKE-001-overlay-event-replayed-twice.

wagon: reconcile-local-store | feature: archive-overlay-events | phase: RED
WMBT: wmbt:reconcile-local-store:Y001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the reconcile-local-store wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.smoke
@pytest.mark.xfail(strict=True, reason="reconcile-local-store not yet implemented (RED; #1400)")
def test_y001_smoke_001_overlay_event_replayed_twice(tmp_path) -> None:
    """Y001-SMOKE-001-overlay-event-replayed-twice — behaviour not yet implemented."""
    raise AssertionError(
        "RED: reconcile-local-store acceptance acc:reconcile-local-store:Y001-SMOKE-001-overlay-event-replayed-twice is not implemented yet"
    )
