# URN: test:spawn-agents:E023-UNIT-001-paste-precedes-jsonl-based-wait
# Acceptance: acc:spawn-agents:E023-UNIT-001-paste-precedes-jsonl-based-wait
# WMBT: wmbt:spawn-agents:E023
# Phase: GREEN
# Layer: backend.unit
# Runtime: python
# Assertion: behavioral
"""E023-UNIT-001 — cmd_spawn paste happens before any JSONL-based wait between surface creation and paste

RED: fails until E023 is implemented — pending E023 GREEN phase.
"""
from __future__ import annotations

import pytest


def test_paste_precedes_jsonl_based_wait():
    pytest.fail(
        "RED: cmd_spawn paste happens before any JSONL-based wait between surface creation and paste — pending E023 GREEN phase"
    )
