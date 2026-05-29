# URN: test:spawn-agents:E028-UNIT-006-cmd-spawn-calls-readiness-probe-not-poll-jsonl
# Acceptance: acc:spawn-agents:E028-UNIT-006-cmd-spawn-calls-readiness-probe-not-poll-jsonl
# WMBT: wmbt:spawn-agents:E028
# Phase: GREEN
# Layer: backend.unit
# Runtime: python
# Assertion: behavioral
"""E028-UNIT-006 — cmd_spawn calls adapter.readiness_probe.wait_for_ready not _poll_for_session_jsonl before paste

RED: fails with AssertionError — cmd_spawn source still calls _wait_for_claude_ready (JSONL-based),
not readiness_probe.wait_for_ready, until E022 GREEN phase.
"""
from __future__ import annotations

import inspect

import atdd.coach.commands.spawn as spawn_mod


def test_cmd_spawn_calls_readiness_probe_not_poll_jsonl():
    source = inspect.getsource(spawn_mod.cmd_spawn)

    # The JSONL-based boot wait (_wait_for_claude_ready) must be retired from cmd_spawn body
    assert "_wait_for_claude_ready" not in source, (
        "cmd_spawn still calls _wait_for_claude_ready (JSONL-based boot wait) — "
        "E022 fix replaces it with adapter.readiness_probe.wait_for_ready"
    )

    # The adapter-agnostic readiness probe must be invoked before the paste
    assert "readiness_probe" in source, (
        "cmd_spawn does not reference readiness_probe — "
        "E022 fix must add adapter.readiness_probe.wait_for_ready call"
    )
