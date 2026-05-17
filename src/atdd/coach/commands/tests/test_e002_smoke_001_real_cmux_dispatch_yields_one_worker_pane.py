# URN: test:consolidate-coach-workspace:wire-layout-into-spawn-path:E002-SMOKE-001-real-cmux-dispatch-yields-one-worker-pane
# Acceptance: acc:consolidate-coach-workspace:E002-SMOKE-001-real-cmux-dispatch-yields-one-worker-pane
# WMBT: wmbt:consolidate-coach-workspace:E002
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""E002-SMOKE-001 — against a real cmux session, dispatching multiple parked
issues produces one coach pane and one worker pane, not N panes.

Opt-in: skipped unless ``ATDD_RUN_SMOKE=1``. Delivered at RED to bind the
``E002-SMOKE-001`` acceptance; exercised at the GREEN→SMOKE transition once
``cmd_spawn`` is wired into ``coach_workspace``.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.platform,
    pytest.mark.smoke,
    pytest.mark.skipif(
        not os.environ.get("ATDD_RUN_SMOKE"),
        reason="opt-in SMOKE test — set ATDD_RUN_SMOKE=1 to run against real cmux",
    ),
]


def test_real_cmux_dispatch_yields_one_worker_pane(tmp_path):
    """Dispatching three parked issues against a real multiplexer leaves
    exactly two panes — one coach pane and one worker pane holding three
    worker surfaces."""
    from atdd.coach.commands import spawn
    from atdd.coach.utils.multiplexer import get_multiplexer

    mx = get_multiplexer()
    issues = [9001, 9002, 9003]

    for issue in issues:
        worktree = tmp_path / f"wt-{issue}"
        worktree.mkdir(parents=True, exist_ok=True)
        spawn.cmd_spawn(
            persona="coder",
            llm="claude-code",
            worktree=worktree,
            issue=issue,
            agent_id=f"coder-{issue}-smoke",
            runtime_root=tmp_path / "rt",
            multiplexer=mx,
        )
        time.sleep(1)

    panes = mx.list_panes()
    assert len(panes) == 2, (
        f"expected exactly two panes (one coach pane, one worker pane); the "
        f"real multiplexer reports {len(panes)}: {[p.get('name') for p in panes]}"
        f" — dispatching {len(issues)} issues must not proliferate panes"
    )
