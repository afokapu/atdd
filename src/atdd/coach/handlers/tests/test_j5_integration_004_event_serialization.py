# URN: test:integration-hardening:coach-state-machine-and-runtime:E001-INTEGRATION-004-event-serialization
# Acceptance: acc:integration-hardening:E001-INTEGRATION-004-event-serialization
# WMBT: wmbt:drive-state-machine:M001
# Phase: RED
# Layer: integration
"""J5-INTEGRATION-004 — simultaneous git-refs + filesystem events on the same
issue produce deterministic transition ordering per timestamp.

The WatcherEventLoop serializes all events on a single ordered queue;
when two events arrive for the same issue they are processed in timestamp
order (oldest first), so transitions are applied in a deterministic
sequence regardless of which watcher fires first.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.platform]


def _make_event(event_type: str, sha: str, issue: int, phase: str, ts: str) -> dict:
    return {
        "event_type": event_type,
        "agent_id": None,
        "timestamp": ts,
        "payload": {
            "sha": sha,
            "parent_sha": None,
            "branch": "feat/test",
            "worktree_path": "/tmp/wt",
            "author": "test <test@example.com>",
            "trailers": {"Issue": str(issue), "Phase": phase},
        },
    }


def test_two_events_applied_in_timestamp_order(tmp_path):
    """When two commit_observed events arrive for the same issue,
    process_pending_events applies them in timestamp order."""
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

    older = _make_event(
        "commit_observed", "sha1", 587, "RED", "2026-05-11T10:00:00.000000Z"
    )
    newer = _make_event(
        "commit_observed", "sha2", 587, "GREEN", "2026-05-11T11:00:00.000000Z"
    )
    queue.put(newer)
    queue.put(older)

    loop.process_pending_events(max_events=2)

    # RED→GREEN applied first (older=RED), then GREEN→SMOKE (newer=GREEN)
    assert sm.phase is Phase.SMOKE
    assert Phase.RED in sm.history
    assert Phase.GREEN in sm.history


def test_simultaneous_events_different_issues_independent(tmp_path):
    """Events for different issues are independent; each machine advances
    only when its own Issue trailer matches."""
    from atdd.coach.commands.event_queue import CoachEventQueue
    from atdd.coach.handlers.state_machine import Phase, initialize_state_machine
    from atdd.coach.handlers.watcher import WatcherEventLoop

    runtime_dir = tmp_path / "runtime"
    queue = CoachEventQueue(runtime_dir=runtime_dir)
    sm_a = initialize_state_machine(issue_number=100)
    sm_b = initialize_state_machine(issue_number=200)
    sm_a.phase = Phase.RED
    sm_b.phase = Phase.RED

    loop = WatcherEventLoop(
        machines=[sm_a, sm_b],
        runtime_dir=runtime_dir,
        queue=queue,
        stale_warn_minutes=None,
        escalation_channel=None,
    )

    ev_a = _make_event(
        "commit_observed", "sha100", 100, "RED", "2026-05-11T10:00:00.000000Z"
    )
    ev_b = _make_event(
        "commit_observed", "sha200", 200, "RED", "2026-05-11T10:00:01.000000Z"
    )
    queue.put(ev_a)
    queue.put(ev_b)

    loop.process_pending_events(max_events=2)

    assert sm_a.phase is Phase.GREEN
    assert sm_b.phase is Phase.GREEN


def test_unknown_event_type_is_ignored_without_crash(tmp_path):
    """An unknown event_type is silently ignored; the state machine is unchanged."""
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

    unknown = {
        "event_type": "alien_invasion",
        "agent_id": None,
        "timestamp": "2026-05-11T10:00:00.000000Z",
        "payload": {},
    }
    queue.put(unknown)
    loop.process_one_event(timeout=0.5)

    assert sm.phase is Phase.RED
