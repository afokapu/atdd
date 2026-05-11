# URN: test:integration-hardening:coach-state-machine-and-runtime:J5-INTEGRATION-001-watcher-drives-state
# Acceptance: acc:integration-hardening:J5-INTEGRATION-001-watcher-drives-state
# WMBT: wmbt:drive-state-machine:M001
# Phase: RED
# Layer: integration
"""J5-INTEGRATION-001 — a git commit on a worktree branch drives a state
transition in the per-issue StateMachine via the watcher event loop.

The state advance is NOT driven by polling; the WatcherEventLoop consumes
a `commit_observed` event (injected via test double) and advances the
state machine. Per spec §4.5 a decision record is appended to decisions.jsonl
before the transition executes.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _make_commit_event(sha: str, issue_number: int, from_phase: str) -> dict:
    """Build a commit_observed event with Issue + Phase trailers."""
    return {
        "event_type": "commit_observed",
        "agent_id": None,
        "timestamp": "2026-05-11T12:00:00.000000Z",
        "payload": {
            "sha": sha,
            "parent_sha": None,
            "branch": "feat/test",
            "worktree_path": "/tmp/wt",
            "author": "test <test@example.com>",
            "trailers": {
                "Issue": str(issue_number),
                "Phase": from_phase,
            },
        },
    }


def test_commit_observed_advances_state_machine(tmp_path):
    """A commit_observed event with Phase: RED + Issue: N drives RED→GREEN
    on the StateMachine for issue N."""
    from atdd.coach.commands.event_queue import CoachEventQueue
    from atdd.coach.handlers.state_machine import (
        Phase,
        StateMachine,
        initialize_state_machine,
    )
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

    event = _make_commit_event(sha="abc123", issue_number=587, from_phase="RED")
    queue.put(event)

    loop.process_one_event(timeout=1.0)

    assert sm.phase is Phase.GREEN
    assert Phase.RED in sm.history


def test_decision_is_written_before_transition(tmp_path):
    """Per spec §4.5: decisions.jsonl receives a record for the phase-transition
    *before* the StateMachine advances (durability first)."""
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

    event = _make_commit_event(sha="def456", issue_number=587, from_phase="RED")
    queue.put(event)
    loop.process_one_event(timeout=1.0)

    decisions_path = runtime_dir / "coach" / "decisions.jsonl"
    assert decisions_path.exists(), "decisions.jsonl must exist after a transition"
    lines = [l for l in decisions_path.read_text().splitlines() if l.strip()]
    assert len(lines) >= 1
    record = json.loads(lines[-1])
    assert record["decision_type"] == "phase-transition"
    assert record["issue_number"] == 587
    assert record["outcome"]["from_phase"] == "RED"
    assert record["outcome"]["to_phase"] == "GREEN"


def test_event_for_different_issue_does_not_advance(tmp_path):
    """A commit_observed event carrying Issue: 999 does NOT advance state
    for issue 587."""
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

    event = _make_commit_event(sha="xyz789", issue_number=999, from_phase="RED")
    queue.put(event)
    result = loop.process_one_event(timeout=0.1)

    assert sm.phase is Phase.RED
    assert result is None or result == "ignored"


def test_watcher_event_loop_exposes_handle_stub():
    """The module-level handle() function is present (required handler interface)."""
    from atdd.coach.handlers.watcher import handle
    from atdd.coach.handlers.state_machine import (
        CoachContext,
        HandlerResult,
        Phase,
        Transition,
    )

    ctx = CoachContext(issue_number=587)
    t = Transition(Phase.RED, Phase.GREEN)
    result = handle(ctx, t)
    assert result in (HandlerResult.NOOP, HandlerResult.HANDLED)
