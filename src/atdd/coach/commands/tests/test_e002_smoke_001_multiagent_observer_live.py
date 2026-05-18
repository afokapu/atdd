# URN: test:observe-and-correct:observer-runtime-and-rules:E002-SMOKE-001-multiagent-observer-live
# Acceptance: acc:observe-and-correct:E002-UNIT-002-multiagent-observer-watches-all-dirs
# Acceptance: acc:observe-and-correct:E002-UNIT-005-observer-terminates-on-coach-exit
# WMBT: wmbt:observe-and-correct:E002
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""E002-SMOKE-001 — MultiAgentObserver live cycle against real file system.

No multiplexer, no subprocess, no network. The observer discovers real
agent dirs from a real tmp filesystem, calls scan_once against them,
then terminates cleanly on stop().

This is NOT gated behind ATDD_RUN_SMOKE because it requires only the
local filesystem — no daemon or external service.
"""
from __future__ import annotations

import time
import threading
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def test_multiagent_observer_live_discovers_and_scans_real_dirs(tmp_path):
    """MultiAgentObserver discovers real agent dirs and calls scan_once."""
    from atdd.coach.commands.observer import MultiAgentObserver

    # Create 3 real agent dirs with output.log
    agents_dir = tmp_path / "agents"
    for name in ("planner-1-abc", "tester-2-def", "coder-3-ghi"):
        d = agents_dir / name
        d.mkdir(parents=True)
        (d / "output.log").write_text(f"[{name}] started\n")

    scanned: list[str] = []
    import atdd.coach.commands.observer as obs_mod

    original_observer_cls = obs_mod.Observer

    class _RecordingObserver(original_observer_cls):
        def scan_once(self) -> None:
            scanned.append(self.agent_id)

    obs_mod.Observer = _RecordingObserver
    try:
        observer = MultiAgentObserver(runtime_root=tmp_path, poll_interval=60.0)
        observer._loop_once()
    finally:
        obs_mod.Observer = original_observer_cls

    assert set(scanned) == {"planner-1-abc", "tester-2-def", "coder-3-ghi"}, (
        f"Expected all 3 agent dirs scanned, got {scanned}"
    )


def test_multiagent_observer_live_start_stop_lifecycle(tmp_path):
    """MultiAgentObserver starts a thread that terminates cleanly on stop()."""
    from atdd.coach.commands.observer import MultiAgentObserver

    observer = MultiAgentObserver(runtime_root=tmp_path, poll_interval=60.0)

    observer.start()
    assert observer._thread is not None
    assert observer._thread.is_alive()

    observer.stop()
    observer._thread.join(timeout=3.0)
    assert not observer._thread.is_alive(), (
        "Observer thread did not terminate within 3.0s after stop()"
    )


def test_multiagent_observer_live_new_agent_picked_up_on_next_iteration(tmp_path):
    """New agent dirs created after start() are picked up on the next _loop_once."""
    from atdd.coach.commands.observer import MultiAgentObserver

    scanned: list[str] = []
    import atdd.coach.commands.observer as obs_mod

    original_observer_cls = obs_mod.Observer

    class _RecordingObserver(original_observer_cls):
        def scan_once(self) -> None:
            scanned.append(self.agent_id)

    obs_mod.Observer = _RecordingObserver
    try:
        observer = MultiAgentObserver(runtime_root=tmp_path, poll_interval=60.0)

        # First iteration: no agents
        observer._loop_once()
        assert scanned == []

        # Add an agent dir
        agent_dir = tmp_path / "agents" / "coder-5-xyz"
        agent_dir.mkdir(parents=True)
        (agent_dir / "output.log").write_text("coder started\n")

        # Second iteration: picks up new agent
        observer._loop_once()
        assert "coder-5-xyz" in scanned, (
            f"Expected coder-5-xyz to be scanned on second iteration, got {scanned}"
        )
    finally:
        obs_mod.Observer = original_observer_cls
