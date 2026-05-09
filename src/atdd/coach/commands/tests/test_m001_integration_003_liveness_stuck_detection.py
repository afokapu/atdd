# URN: test:drive-state-machine:coach-state-machine-and-runtime:M001-INTEGRATION-003-liveness-stuck-detection
# Acceptance: acc:drive-state-machine:M001-INTEGRATION-003-liveness-stuck-detection
# WMBT: wmbt:drive-state-machine:M001
# Phase: RED
# Layer: integration
"""M001-INTEGRATION-003 — the 30s liveness checker emits a ``stuck`` event
(``process_silence`` per the schema) when an agent's
``process_heartbeat.json`` (``heartbeat.json`` per ``runtime-layout.md``)
is older than ``coach.process_silence_seconds``.

Bounded emissions: one ``process_silence`` per silence window, not one
per timer tick — dedup at the consumer per ``event-semantics.md`` natural
key ``(agent_id, payload.silence_window_started_at)``.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _agent_dir(runtime_dir: Path, agent_id: str) -> Path:
    d = runtime_dir / "agents" / agent_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_heartbeat(agent_dir: Path, observed_at: datetime, *, pid: int = 1234) -> None:
    (agent_dir / "heartbeat.json").write_text(
        json.dumps(
            {
                "pid": pid,
                "observed_at": observed_at.astimezone(timezone.utc).isoformat(),
                "status": "alive",
            }
        )
    )


def test_no_stuck_event_when_heartbeat_is_fresh(tmp_path):
    from atdd.coach.commands.watchers import CoachEventQueue, LivenessChecker

    queue = CoachEventQueue(runtime_dir=tmp_path)
    now = datetime(2026, 5, 9, 12, 0, 0, tzinfo=timezone.utc)
    checker = LivenessChecker(
        runtime_dir=tmp_path,
        queue=queue,
        silence_seconds=30,
        clock=lambda: now,
    )

    agent_dir = _agent_dir(tmp_path, "agent-fresh")
    _write_heartbeat(agent_dir, now - timedelta(seconds=5))

    checker.tick()
    assert queue.drain() == []


def test_stuck_event_emitted_when_silence_threshold_exceeded(tmp_path):
    from atdd.coach.commands.watchers import CoachEventQueue, LivenessChecker

    queue = CoachEventQueue(runtime_dir=tmp_path)
    now = datetime(2026, 5, 9, 12, 0, 0, tzinfo=timezone.utc)
    last_hb = now - timedelta(seconds=120)
    checker = LivenessChecker(
        runtime_dir=tmp_path,
        queue=queue,
        silence_seconds=30,
        clock=lambda: now,
    )

    agent_dir = _agent_dir(tmp_path, "agent-stuck")
    _write_heartbeat(agent_dir, last_hb)

    checker.tick()
    events = [e for e in queue.drain() if e["event_type"] == "process_silence"]
    assert len(events) == 1
    payload = events[0]["payload"]
    assert events[0]["agent_id"] == "agent-stuck"
    assert payload["last_heartbeat_at"] == last_hb.isoformat()
    assert payload["elapsed_seconds"] == 120
    assert "silence_window_started_at" in payload


def test_emissions_are_bounded_one_per_silence_window(tmp_path):
    """Three timer ticks, all within the same silence window — one event."""
    from atdd.coach.commands.watchers import CoachEventQueue, LivenessChecker

    queue = CoachEventQueue(runtime_dir=tmp_path)
    now = datetime(2026, 5, 9, 12, 0, 0, tzinfo=timezone.utc)
    last_hb = now - timedelta(seconds=120)
    clock = {"now": now}
    checker = LivenessChecker(
        runtime_dir=tmp_path,
        queue=queue,
        silence_seconds=30,
        clock=lambda: clock["now"],
    )
    agent_dir = _agent_dir(tmp_path, "agent-x")
    _write_heartbeat(agent_dir, last_hb)

    checker.tick()
    clock["now"] = now + timedelta(seconds=30)
    checker.tick()
    clock["now"] = now + timedelta(seconds=60)
    checker.tick()

    events = [e for e in queue.drain() if e["event_type"] == "process_silence"]
    assert len(events) == 1, (
        f"expected 1 process_silence per silence window, got {len(events)}"
    )


def test_new_silence_window_after_heartbeat_resumed_then_stops_again(tmp_path):
    """Heartbeat → silence → heartbeat → silence: two distinct windows,
    two events with distinct silence_window_started_at."""
    from atdd.coach.commands.watchers import CoachEventQueue, LivenessChecker

    queue = CoachEventQueue(runtime_dir=tmp_path)
    now = datetime(2026, 5, 9, 12, 0, 0, tzinfo=timezone.utc)
    clock = {"now": now}
    checker = LivenessChecker(
        runtime_dir=tmp_path,
        queue=queue,
        silence_seconds=30,
        clock=lambda: clock["now"],
    )
    agent_dir = _agent_dir(tmp_path, "agent-yo")

    # Window 1: stale heartbeat → emit
    _write_heartbeat(agent_dir, now - timedelta(seconds=120))
    checker.tick()

    # Heartbeat resumes (fresh heartbeat) — silence resolved
    clock["now"] = now + timedelta(seconds=60)
    _write_heartbeat(agent_dir, clock["now"] - timedelta(seconds=2))
    checker.tick()

    # Window 2: stops again → emit a fresh process_silence
    clock["now"] = now + timedelta(seconds=200)
    checker.tick()

    events = [e for e in queue.drain() if e["event_type"] == "process_silence"]
    assert len(events) == 2
    assert (
        events[0]["payload"]["silence_window_started_at"]
        != events[1]["payload"]["silence_window_started_at"]
    )


def test_missing_heartbeat_file_is_treated_as_stuck(tmp_path):
    """An agent directory that exists but has no heartbeat.json is stuck."""
    from atdd.coach.commands.watchers import CoachEventQueue, LivenessChecker

    queue = CoachEventQueue(runtime_dir=tmp_path)
    now = datetime(2026, 5, 9, 12, 0, 0, tzinfo=timezone.utc)
    checker = LivenessChecker(
        runtime_dir=tmp_path,
        queue=queue,
        silence_seconds=30,
        clock=lambda: now,
    )

    _agent_dir(tmp_path, "agent-noheartbeat")  # directory but no file
    checker.tick()
    events = [e for e in queue.drain() if e["event_type"] == "process_silence"]
    assert len(events) == 1
    assert events[0]["agent_id"] == "agent-noheartbeat"
