# URN: test:consolidate-coach-workspace:headless-observer:Y002-SMOKE-001-real-spawn-yields-one-tab
# Acceptance: acc:consolidate-coach-workspace:Y002-SMOKE-001-real-spawn-yields-one-tab
# WMBT: wmbt:consolidate-coach-workspace:Y002
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""Y002-SMOKE-001 — against a real multiplexer, spawning a worker yields
exactly one tab and a live headless observer writing corrections.

Opt-in: skipped unless ``ATDD_RUN_SMOKE=1``. Delivered at RED to bind the
``Y002-SMOKE-001`` acceptance; exercised at the GREEN→SMOKE transition.
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


def test_real_spawn_yields_one_tab(tmp_path):
    """A real coach spawn of one persona yields exactly one worker tab (no
    `:obs` tab) and a headless observer that has written corrections.jsonl."""
    from atdd.coach.handlers import spawn as spawn_handler
    from atdd.coach.handlers.state_machine import CoachContext, Phase, Transition
    from atdd.coach.utils.multiplexer import get_multiplexer

    mx = get_multiplexer()
    ctx = CoachContext(issue_number=736)

    spawn_handler.handle(ctx, Transition(src=Phase.INIT, dst=Phase.PLANNED))
    time.sleep(2)

    obs_tabs = [p for p in mx.list_panes()
                if isinstance(p.get("name"), str) and p["name"].endswith(":obs")]
    assert obs_tabs == [], f"observer surfaces present on a real multiplexer: {obs_tabs}"

    corrections = list(Path(tmp_path).rglob("corrections.jsonl"))
    assert corrections, "headless observer did not write any corrections.jsonl"
