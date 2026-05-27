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
    pytest.fail(
        "RED: Deployed cmd_spawn has no JSONL-based call between surface creation and launch-prompt paste — pending E023 GREEN phase"
    )
