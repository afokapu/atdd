# URN: test:observe-and-correct:worker-coach-event-loop:M005-UNIT-001-observer-emits-heartbeat-on-cadence
# Acceptance: acc:observe-and-correct:M005-UNIT-001-observer-emits-heartbeat-on-cadence
# WMBT: wmbt:observe-and-correct:M005
# Phase: RED
# Layer: application
"""M005-UNIT-001 — the observer sidecar emits an ``atdd agent heartbeat``
event for its worker once per scan cycle.

Issue #731 Phase 2 — a coach-spawned worker's ``events.jsonl`` is empty
because nothing emits heartbeats; the observer (a per-worker LLM-neutral
Python sidecar) must emit them itself.

RED: ``Observer.scan_once`` evaluates rules but emits no ``heartbeat``
event, so the worker's ``events.jsonl`` never gains heartbeat records.
"""
from __future__ import annotations

import json
from pathlib import Path

OBSERVER_ID = "tester-731-hb01-observer"
WORKER_ID = "tester-731-hb01"


def _heartbeat_events(runtime: Path, worker_id: str) -> list[dict]:
    path = runtime / "agents" / worker_id / "events.jsonl"
    if not path.exists():
        return []
    records = [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]
    return [r for r in records if r.get("event_type") == "heartbeat"]


def _observer(runtime: Path):
    from atdd.coach.commands.observer import Observer

    return Observer(agent_id=OBSERVER_ID, runtime_dir=runtime, rules_dir=None)


def test_no_heartbeat_before_the_first_scan(tmp_path):
    runtime = tmp_path / "rt"
    _observer(runtime)
    assert _heartbeat_events(runtime, WORKER_ID) == []


def test_each_scan_emits_exactly_one_worker_heartbeat(tmp_path):
    runtime = tmp_path / "rt"
    obs = _observer(runtime)
    for _ in range(3):
        obs.scan_once()
    assert len(_heartbeat_events(runtime, WORKER_ID)) == 3


def test_emitted_heartbeat_carries_the_worker_agent_id(tmp_path):
    runtime = tmp_path / "rt"
    obs = _observer(runtime)
    obs.scan_once()
    events = _heartbeat_events(runtime, WORKER_ID)
    assert events, "observer emitted no heartbeat event for its worker"
    assert all(e.get("agent_id") == WORKER_ID for e in events)
