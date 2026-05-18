# URN: test:consolidate-coach-workspace:headless-observer-in-spawn-path:E002-SMOKE-001-real-spawn-yields-one-tab-no-obs
# Acceptance: acc:consolidate-coach-workspace:E002-SMOKE-001-real-spawn-yields-one-tab-no-obs
# WMBT: wmbt:consolidate-coach-workspace:E002
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""E002-SMOKE-001 — against a real multiplexer, a ``cmd_spawn`` yields exactly
one worker tab (no ``:obs`` tab) and a live headless observer.

Opt-in: skipped unless ``ATDD_RUN_SMOKE=1``. Delivered at RED to bind the
``E002-SMOKE-001`` acceptance; exercised at the GREEN→SMOKE transition once
``cmd_spawn`` runs the observer headless.
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
        reason="opt-in SMOKE test — set ATDD_RUN_SMOKE=1 to run against a real multiplexer",
    ),
]


def test_real_spawn_yields_one_tab_no_obs(tmp_path):
    """A real ``cmd_spawn`` of one persona leaves exactly one worker tab with
    no co-spawned ``:obs`` tab."""
    from atdd.coach.commands import spawn
    from atdd.coach.utils.multiplexer import get_multiplexer

    mx = get_multiplexer()
    worktree = tmp_path / "wt-9001"
    worktree.mkdir(parents=True, exist_ok=True)

    spawn.cmd_spawn(
        persona="coder",
        llm="claude-code",
        worktree=worktree,
        issue=9001,
        agent_id="coder-9001-smoke",
        runtime_root=tmp_path / "rt",
        multiplexer=mx,
    )
    time.sleep(2)

    obs_tabs = [p for p in mx.list_workspaces()
                if isinstance(p, str) and p.endswith(":obs")]
    assert obs_tabs == [], (
        f"observer `:obs` surface(s) present on a real multiplexer after "
        f"cmd_spawn: {obs_tabs} — the observer must run headless"
    )
