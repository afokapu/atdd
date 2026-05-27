# URN: test:spawn-agents:E023-UNIT-001-paste-precedes-jsonl-based-wait
# Acceptance: acc:spawn-agents:E023-UNIT-001-paste-precedes-jsonl-based-wait
# WMBT: wmbt:spawn-agents:E023
# Phase: GREEN
# Layer: backend.unit
# Runtime: python
# Assertion: behavioral
"""E023-UNIT-001 — cmd_spawn paste happens before any JSONL-based wait between surface creation and paste

RED: AssertionError — cmd_spawn source still calls _wait_for_claude_ready (JSONL-based gate)
before paste; readiness_probe not present until E023 GREEN phase.
"""
from __future__ import annotations

import inspect

import atdd.coach.commands.spawn as spawn_mod


def test_paste_precedes_jsonl_based_wait():
    source = inspect.getsource(spawn_mod.cmd_spawn)

    # No JSONL-based boot wait between surface creation and paste
    assert "_wait_for_claude_ready" not in source, (
        "cmd_spawn source still calls _wait_for_claude_ready (JSONL-based gate) "
        "before paste — E023 fix must retire this pre-paste JSONL check"
    )

    # Adapter-agnostic readiness probe must gate the paste
    assert "readiness_probe" in source or "wait_for_ready" in source, (
        "cmd_spawn source does not call readiness_probe.wait_for_ready before paste — "
        "E023 fix must add the adapter-agnostic probe call"
    )

    # _assert_worker_processing is preserved post-paste
    assert "_assert_worker_processing" in source, (
        "cmd_spawn source no longer calls _assert_worker_processing — "
        "E023 requires this post-paste JSONL-growth gate to be retained"
    )
