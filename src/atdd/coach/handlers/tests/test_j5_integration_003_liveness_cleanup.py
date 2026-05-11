# URN: test:integration-hardening:coach-state-machine-and-runtime:J5-INTEGRATION-003-liveness-cleanup
# Acceptance: acc:integration-hardening:J5-INTEGRATION-003-liveness-cleanup
# WMBT: wmbt:drive-state-machine:M001
# Phase: RED
# Layer: integration
"""J5-INTEGRATION-003 — `atdd coach` exits cleanly on SIGTERM; the watcher
subprocess is terminated; partial state is preserved in decisions.jsonl.

Uses WatcherEventLoop.shutdown() (the SIGTERM handler's body) to verify
that the stop sequence persists checkpoint + flushes partial state.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def test_shutdown_stops_runtime_watcher(tmp_path):
    """WatcherEventLoop.shutdown() stops the RuntimeWatcher background thread."""
    from atdd.coach.commands.event_queue import CoachEventQueue
    from atdd.coach.commands.runtime_watcher import RuntimeWatcher
    from atdd.coach.handlers.state_machine import initialize_state_machine
    from atdd.coach.handlers.watcher import WatcherEventLoop

    runtime_dir = tmp_path / "runtime"
    queue = CoachEventQueue(runtime_dir=runtime_dir)
    sm = initialize_state_machine(issue_number=587)

    loop = WatcherEventLoop(
        machines=[sm],
        runtime_dir=runtime_dir,
        queue=queue,
        stale_warn_minutes=None,
        escalation_channel=None,
    )
    loop.start_background_watchers()
    assert loop.runtime_watcher._thread is not None
    assert loop.runtime_watcher._thread.is_alive()

    loop.shutdown()

    # RuntimeWatcher.stop() joins and sets _thread = None
    assert loop.runtime_watcher._thread is None


def test_shutdown_persists_watcher_checkpoint(tmp_path):
    """shutdown() calls RuntimeWatcher.persist_checkpoint() so reattachment
    is lossless on the next coach --resume."""
    from atdd.coach.commands.event_queue import CoachEventQueue
    from atdd.coach.handlers.state_machine import initialize_state_machine
    from atdd.coach.handlers.watcher import WatcherEventLoop

    runtime_dir = tmp_path / "runtime"
    queue = CoachEventQueue(runtime_dir=runtime_dir)
    sm = initialize_state_machine(issue_number=587)

    loop = WatcherEventLoop(
        machines=[sm],
        runtime_dir=runtime_dir,
        queue=queue,
        stale_warn_minutes=None,
        escalation_channel=None,
    )
    loop.start_background_watchers()
    loop.shutdown()

    checkpoint = runtime_dir / "coach" / "watcher-checkpoint.json"
    assert checkpoint.exists(), "watcher-checkpoint.json must exist after shutdown"


def test_shutdown_writes_partial_state_to_decisions(tmp_path):
    """After a state advance followed by shutdown(), decisions.jsonl is non-empty
    (partial state is preserved even if coach exits mid-run)."""
    from atdd.coach.commands.event_queue import CoachEventQueue
    from atdd.coach.handlers.state_machine import Phase, initialize_state_machine
    from atdd.coach.handlers.watcher import WatcherEventLoop

    runtime_dir = tmp_path / "runtime"
    queue = CoachEventQueue(runtime_dir=runtime_dir)
    sm = initialize_state_machine(issue_number=587)
    sm.phase = Phase.RED

    loop = WatcherEventLoop(
        machines=[sm],
        runtime_dir=runtime_dir,
        queue=queue,
        stale_warn_minutes=None,
        escalation_channel=None,
    )

    event = {
        "event_type": "commit_observed",
        "agent_id": None,
        "timestamp": "2026-05-11T12:00:00.000000Z",
        "payload": {
            "sha": "cafe1234",
            "parent_sha": None,
            "branch": "feat/test",
            "worktree_path": "/tmp/wt",
            "author": "test <test@example.com>",
            "trailers": {"Issue": "587", "Phase": "RED"},
        },
    }
    queue.put(event)
    loop.process_one_event(timeout=1.0)

    loop.shutdown()

    decisions_path = runtime_dir / "coach" / "decisions.jsonl"
    assert decisions_path.exists()
    content = decisions_path.read_text()
    lines = [l for l in content.splitlines() if l.strip()]
    assert len(lines) >= 1


def test_shutdown_idempotent(tmp_path):
    """Calling shutdown() twice does not raise."""
    from atdd.coach.commands.event_queue import CoachEventQueue
    from atdd.coach.handlers.state_machine import initialize_state_machine
    from atdd.coach.handlers.watcher import WatcherEventLoop

    runtime_dir = tmp_path / "runtime"
    queue = CoachEventQueue(runtime_dir=runtime_dir)
    sm = initialize_state_machine(issue_number=587)

    loop = WatcherEventLoop(
        machines=[sm],
        runtime_dir=runtime_dir,
        queue=queue,
        stale_warn_minutes=None,
        escalation_channel=None,
    )
    loop.start_background_watchers()
    loop.shutdown()
    loop.shutdown()  # must not raise
