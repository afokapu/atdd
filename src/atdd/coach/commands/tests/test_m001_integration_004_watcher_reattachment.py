# URN: test:drive-state-machine:coach-state-machine-and-runtime:M001-INTEGRATION-004-watcher-reattachment
# Acceptance: acc:drive-state-machine:M001-INTEGRATION-004-watcher-reattachment
# WMBT: wmbt:drive-state-machine:M001
# Phase: RED
# Layer: integration
"""M001-INTEGRATION-004 — killing the watcher mid-run and restarting it
loses no events from disk-persisted state and emits no duplicates for
in-flight transitions whose handlers already completed (per the
``event-semantics.md`` reattachment contract from #483).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _agent_dir(runtime_dir: Path, agent_id: str) -> Path:
    d = runtime_dir / "agents" / agent_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _seed_events(agent_dir: Path, events: list[dict]) -> None:
    path = agent_dir / "events.jsonl"
    with path.open("a") as fh:
        for ev in events:
            fh.write(json.dumps(ev) + "\n")


def test_replay_does_not_re_emit_handled_exactly_once_events(tmp_path):
    """``agent_spawned`` is exactly-once-replay-cached: on resume the prior
    event is republished from the durable ledger; a second restart does
    NOT produce a fresh emission."""
    from atdd.coach.commands.watchers import CoachEventQueue, RuntimeWatcher

    runtime = tmp_path
    agent_dir = _agent_dir(runtime, "agent-rsm")
    _seed_events(
        agent_dir,
        [
            {
                "event_type": "agent_spawned",
                "agent_id": "agent-rsm",
                "timestamp": "2026-05-09T13:45:00Z",
                "payload": {"pid": 100},
            }
        ],
    )

    queue = CoachEventQueue(runtime_dir=runtime)
    watcher_a = RuntimeWatcher(runtime_dir=runtime, queue=queue, poll_interval=0.05)
    watcher_a.replay_from_disk()
    first_pass = [e for e in queue.drain() if e["event_type"] == "agent_spawned"]

    # Mark this event-handler as completed by recording it in the watcher checkpoint.
    watcher_a.mark_handled(first_pass[0])
    watcher_a.persist_checkpoint()

    # Simulate a restart with the same on-disk state.
    queue2 = CoachEventQueue(runtime_dir=runtime)
    watcher_b = RuntimeWatcher(runtime_dir=runtime, queue=queue2, poll_interval=0.05)
    watcher_b.replay_from_disk()
    second_pass = [e for e in queue2.drain() if e["event_type"] == "agent_spawned"]

    assert second_pass == [], (
        "exactly-once event re-fired after restart — checkpoint did not persist handled events"
    )


def test_replay_does_not_lose_unhandled_events(tmp_path):
    """An event whose handler did NOT complete must be redelivered after
    restart (durability via append-only state)."""
    from atdd.coach.commands.watchers import CoachEventQueue, RuntimeWatcher

    runtime = tmp_path
    agent_dir = _agent_dir(runtime, "agent-pending")
    _seed_events(
        agent_dir,
        [
            {
                "event_type": "validation_pending",
                "agent_id": "agent-pending",
                "timestamp": "2026-05-09T14:00:00Z",
                "payload": {"phase": "GREEN", "sha": "abc"},
            }
        ],
    )

    queue = CoachEventQueue(runtime_dir=runtime)
    watcher = RuntimeWatcher(runtime_dir=runtime, queue=queue, poll_interval=0.05)
    watcher.replay_from_disk()
    # Crash without marking handled.
    watcher.persist_checkpoint()

    queue2 = CoachEventQueue(runtime_dir=runtime)
    watcher2 = RuntimeWatcher(runtime_dir=runtime, queue=queue2, poll_interval=0.05)
    watcher2.replay_from_disk()
    pending = [e for e in queue2.drain() if e["event_type"] == "validation_pending"]
    assert len(pending) == 1
    assert pending[0]["payload"]["sha"] == "abc"


def test_replay_suppressed_events_not_re_emitted(tmp_path):
    """``heartbeat`` is replay-suppressed: post-restart, prior heartbeats are
    NOT re-published, even if not marked handled."""
    from atdd.coach.commands.watchers import CoachEventQueue, RuntimeWatcher

    runtime = tmp_path
    agent_dir = _agent_dir(runtime, "agent-hb")
    _seed_events(
        agent_dir,
        [
            {
                "event_type": "heartbeat",
                "agent_id": "agent-hb",
                "timestamp": "2026-05-09T14:00:00Z",
                "payload": {"observed_at": "2026-05-09T14:00:00Z"},
            },
            {
                "event_type": "heartbeat",
                "agent_id": "agent-hb",
                "timestamp": "2026-05-09T14:01:00Z",
                "payload": {"observed_at": "2026-05-09T14:01:00Z"},
            },
        ],
    )

    queue = CoachEventQueue(runtime_dir=runtime)
    watcher = RuntimeWatcher(runtime_dir=runtime, queue=queue, poll_interval=0.05)
    watcher.replay_from_disk()

    hb = [e for e in queue.drain() if e["event_type"] == "heartbeat"]
    assert hb == [], "replay-suppressed event re-fired after restart"


def test_at_least_once_replay_dedupes_via_natural_key(tmp_path):
    """``commit_observed`` is at-least-once: replay republishes the event,
    and the queue's idempotency layer dedupes by ``payload.sha`` so that a
    consumer reading the queue sees the event exactly once even if replay
    overlaps with a fresh emission."""
    from atdd.coach.commands.watchers import CoachEventQueue

    runtime = tmp_path
    queue = CoachEventQueue(runtime_dir=runtime)

    ev = {
        "event_type": "commit_observed",
        "agent_id": "agent-c",
        "timestamp": "2026-05-09T14:02:00Z",
        "payload": {"sha": "deadbeef", "branch": "main", "worktree_path": "/x"},
    }

    queue.put(ev)
    queue.put(dict(ev))  # duplicate emission within same run

    drained = [e for e in queue.drain() if e["event_type"] == "commit_observed"]
    assert len(drained) == 1, (
        f"queue idempotency should dedupe at-least-once events; got {len(drained)}"
    )
