# URN: test:reconcile-local-store:record-overlay-events:E001-UNIT-001-authoring-command-appends-overlay-event
# Acceptance: acc:reconcile-local-store:E001-UNIT-001-authoring-command-appends-overlay-event
# WMBT: wmbt:reconcile-local-store:E001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:reconcile-local-store:E001-UNIT-001-authoring-command-appends-overlay-event — fails until the reconcile-local-store wagon implements it (train 0006). Refs #1400.
"""RED skeleton for acc:reconcile-local-store:E001-UNIT-001-authoring-command-appends-overlay-event.

wagon: reconcile-local-store | feature: record-overlay-events | phase: RED
WMBT: wmbt:reconcile-local-store:E001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the reconcile-local-store wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="reconcile-local-store not yet implemented (RED; #1400)")
def test_e001_unit_001_authoring_command_appends_overlay_event(tmp_path) -> None:
    """E001-UNIT-001-authoring-command-appends-overlay-event — behaviour not yet implemented."""
    raise AssertionError(
        "RED: reconcile-local-store acceptance acc:reconcile-local-store:E001-UNIT-001-authoring-command-appends-overlay-event is not implemented yet"
    )
