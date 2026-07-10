# URN: test:isolate-provider-boundary:define-provider-interface:D001-UNIT-001-rejects-non-bot-external-ref
# Acceptance: acc:isolate-provider-boundary:D001-UNIT-001-rejects-non-bot-external-ref
# WMBT: wmbt:isolate-provider-boundary:D001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:isolate-provider-boundary:D001-UNIT-001-rejects-non-bot-external-ref — fails until the isolate-provider-boundary wagon implements it. Refs #1400.
"""RED skeleton for acc:isolate-provider-boundary:D001-UNIT-001-rejects-non-bot-external-ref.

wagon: isolate-provider-boundary | feature: define-provider-interface | phase: RED
WMBT: wmbt:isolate-provider-boundary:D001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the isolate-provider-boundary wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="isolate-provider-boundary not yet implemented (RED; #1400)")
def test_d001_unit_001_rejects_non_bot_external_ref(tmp_path) -> None:
    """D001-UNIT-001-rejects-non-bot-external-ref — behaviour not yet implemented."""
    raise AssertionError(
        "RED: isolate-provider-boundary acceptance acc:isolate-provider-boundary:D001-UNIT-001-rejects-non-bot-external-ref is not implemented yet"
    )
