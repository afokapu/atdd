# URN: test:drive-state-machine:coach-state-machine-and-runtime:M001-INTEGRATION-001-runtime-event-latency
# Acceptance: acc:drive-state-machine:M001-INTEGRATION-001-runtime-event-latency
# WMBT: wmbt:drive-state-machine:M001
# Phase: RED
# Layer: integration
"""M001-INTEGRATION-001 — runtime watcher emits a coach event within 1s of
a file change in ``.atdd/runtime/agents/<id>/``.

Per spec §4.4 the runtime watcher tracks four files per agent
(``heartbeat.json``, ``events.jsonl``, ``escalations.jsonl``,
``corrections.jsonl``). On change, the watcher emits an event onto the
**single coach event queue** (not per-watcher queues). The payload
conforms to ``runtime-event.schema.json`` (#483).

The 1s latency budget covers the inotify/fswatch path. Tests use a short
poll interval to avoid platform-specific dependencies; the contract being
tested is *propagation latency*, not the FS-event mechanism itself.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _agent_dir(runtime_dir: Path, agent_id: str) -> Path:
    d = runtime_dir / "agents" / agent_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_event_queue_is_single_and_shared(tmp_path):
    """Per spec §4.4: all watchers feed one shared queue, not per-watcher."""
    from atdd.coach.commands.watchers import CoachEventQueue, RuntimeWatcher

    queue = CoachEventQueue(runtime_dir=tmp_path)
    watcher = RuntimeWatcher(runtime_dir=tmp_path, queue=queue)
    assert watcher.queue is queue


def test_heartbeat_write_emits_event_within_one_second(tmp_path):
    """A new heartbeat.json file under .atdd/runtime/agents/<id>/ produces a
    runtime event on the shared queue within 1s."""
    from atdd.coach.commands.watchers import CoachEventQueue, RuntimeWatcher

    queue = CoachEventQueue(runtime_dir=tmp_path)
    watcher = RuntimeWatcher(runtime_dir=tmp_path, queue=queue, poll_interval=0.05)

    agent_dir = _agent_dir(tmp_path, "agent-J5-runtime-test")
    watcher.start()
    try:
        start = time.monotonic()
        (agent_dir / "heartbeat.json").write_text(
            json.dumps({"pid": 1234, "observed_at": "2026-05-09T13:45:02Z", "status": "alive"})
        )
        event = queue.get(timeout=1.0)
        elapsed = time.monotonic() - start
    finally:
        watcher.stop()

    assert event is not None, "watcher did not emit within the 1s budget"
    assert elapsed < 1.0, f"latency {elapsed:.3f}s exceeded 1s budget"
    assert event["event_type"] == "heartbeat"
    assert event["agent_id"] == "agent-J5-runtime-test"


def test_event_payload_conforms_to_runtime_event_schema(tmp_path):
    """Emitted events are valid against runtime-event.schema.json (#483)."""
    from jsonschema import Draft202012Validator
    import atdd
    from atdd.coach.commands.watchers import CoachEventQueue, RuntimeWatcher

    schema_path = (
        Path(atdd.__file__).resolve().parent
        / "coach"
        / "schemas"
        / "runtime-event.schema.json"
    )
    validator = Draft202012Validator(json.loads(schema_path.read_text()))

    queue = CoachEventQueue(runtime_dir=tmp_path)
    watcher = RuntimeWatcher(runtime_dir=tmp_path, queue=queue, poll_interval=0.05)
    agent_dir = _agent_dir(tmp_path, "agent-A")

    watcher.start()
    try:
        (agent_dir / "events.jsonl").write_text(
            json.dumps(
                {
                    "event_type": "agent_spawned",
                    "agent_id": "agent-A",
                    "timestamp": "2026-05-09T13:45:02Z",
                    "payload": {"pid": 7777},
                }
            )
            + "\n"
        )
        event = queue.get(timeout=1.0)
    finally:
        watcher.stop()

    assert event is not None
    errors = list(validator.iter_errors(event))
    assert not errors, f"event payload is not schema-valid: {errors}"


def test_all_four_runtime_files_are_watched(tmp_path):
    """Per spec §4.4 the watcher tracks heartbeat.json, events.jsonl,
    escalations.jsonl, and corrections.jsonl. Writing to each must
    surface an event."""
    from atdd.coach.commands.watchers import CoachEventQueue, RuntimeWatcher

    queue = CoachEventQueue(runtime_dir=tmp_path)
    watcher = RuntimeWatcher(runtime_dir=tmp_path, queue=queue, poll_interval=0.05)
    agent_dir = _agent_dir(tmp_path, "agent-multi")

    watcher.start()
    try:
        (agent_dir / "heartbeat.json").write_text(
            json.dumps({"pid": 1, "observed_at": "2026-05-09T00:00:00Z", "status": "alive"})
        )
        (agent_dir / "events.jsonl").write_text(
            json.dumps(
                {
                    "event_type": "validation_pending",
                    "agent_id": "agent-multi",
                    "timestamp": "2026-05-09T00:00:01Z",
                    "payload": {},
                }
            )
            + "\n"
        )
        (agent_dir / "corrections.jsonl").write_text(
            json.dumps({"agent_id": "agent-multi", "rule_id": "r1", "detected_at": "2026-05-09T00:00:02Z"})
            + "\n"
        )
        (agent_dir / "escalations.jsonl").write_text(
            json.dumps({"agent_id": "agent-multi", "judgment_id": "j1", "target": "human"})
            + "\n"
        )
        deadline = time.monotonic() + 2.0
        seen_sources: set[str] = set()
        while time.monotonic() < deadline and len(seen_sources) < 4:
            ev = queue.get(timeout=0.2)
            if ev is None:
                continue
            seen_sources.add(ev.get("_source_file") or ev.get("event_type"))
    finally:
        watcher.stop()

    assert len(seen_sources) >= 4, (
        f"watcher did not surface events from all four runtime files; saw: {seen_sources}"
    )
