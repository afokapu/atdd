# URN: test:spawn-agents:E022-UNIT-006-cmd-spawn-calls-readiness-probe-not-poll-jsonl
# Acceptance: acc:spawn-agents:E022-UNIT-006-cmd-spawn-calls-readiness-probe-not-poll-jsonl
# WMBT: wmbt:spawn-agents:E022
# Phase: GREEN
# Layer: backend.unit
# Runtime: python
# Assertion: behavioral
"""E022-UNIT-006 — cmd_spawn calls adapter.readiness_probe.wait_for_ready not _poll_for_session_jsonl before paste

RED: fails until cmd_spawn readiness_probe dispatch is implemented — pending E022 GREEN phase.
"""
from __future__ import annotations

import pytest


def test_cmd_spawn_calls_readiness_probe_not_poll_jsonl():
    pytest.fail(
        "RED: cmd_spawn calls adapter.readiness_probe.wait_for_ready not _poll_for_session_jsonl before paste — pending E022 GREEN phase"
    )
