# URN: test:spawn-agents:E023-SMOKE-001-deployed-cmd-spawn-order-is-probe-then-paste-then-jsonl
# Acceptance: acc:spawn-agents:E023-SMOKE-001-deployed-cmd-spawn-order-is-probe-then-paste-then-jsonl
# WMBT: wmbt:spawn-agents:E023
# Phase: SMOKE
# Layer: backend.smoke
# Runtime: python
# Assertion: behavioral
"""E023-SMOKE-001 — Deployed cmd_spawn has no JSONL-based call between surface creation and launch-prompt paste

RED: fails until E023 is implemented — pending E023 GREEN phase.
"""
from __future__ import annotations

import os

import pytest

pytestmark = [pytest.mark.smoke]


@pytest.mark.skipif(
    not os.environ.get("ATDD_RUN_SMOKE"),
    reason="E023-SMOKE-001 requires ATDD_RUN_SMOKE=1",
)
def test_deployed_cmd_spawn_order_is_probe_then_paste_then_jsonl():
    import inspect

    import atdd.coach.commands.spawn as spawn_mod

    source = inspect.getsource(spawn_mod.cmd_spawn)

    # No JSONL-based boot wait in the pre-paste position
    assert "_wait_for_claude_ready" not in source, (
        "Deployed cmd_spawn source still calls _wait_for_claude_ready (JSONL-based gate) — "
        "E023 fix must retire this pre-paste JSONL check"
    )

    # Adapter-agnostic readiness probe must appear before paste
    probe_idx = -1
    paste_idx = -1
    for kw in ("readiness_probe", "wait_for_ready"):
        idx = source.find(kw)
        if idx != -1 and (probe_idx == -1 or idx < probe_idx):
            probe_idx = idx
    paste_idx = source.find("paste_text")

    assert probe_idx != -1, (
        "Deployed cmd_spawn source does not call readiness_probe / wait_for_ready — "
        "E023 fix must add the adapter-agnostic probe call"
    )
    assert paste_idx != -1, "paste_text not found in cmd_spawn source"
    assert probe_idx < paste_idx, (
        f"readiness_probe (pos {probe_idx}) does not appear before paste_text (pos {paste_idx}) "
        "in cmd_spawn source — E023 fix must ensure probe gates the paste"
    )

    # _assert_worker_processing is retained after paste
    awp_idx = source.find("_assert_worker_processing")
    assert awp_idx != -1, (
        "_assert_worker_processing not found in deployed cmd_spawn — "
        "E023 requires JSONL-growth post-paste verification to be preserved"
    )
    assert awp_idx > paste_idx, (
        f"_assert_worker_processing (pos {awp_idx}) appears before paste_text (pos {paste_idx}) — "
        "E023 requires _assert_worker_processing to be a post-paste gate"
    )
