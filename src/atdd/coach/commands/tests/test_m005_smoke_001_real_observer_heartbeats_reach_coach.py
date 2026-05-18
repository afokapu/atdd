# URN: test:observe-and-correct:worker-coach-event-loop:M005-SMOKE-001-real-observer-heartbeats-reach-coach
# Acceptance: acc:observe-and-correct:M005-SMOKE-001-real-observer-heartbeats-reach-coach
# WMBT: wmbt:observe-and-correct:M005
# Phase: SMOKE
# Layer: integration
# Harness: smoke/backend
"""M005-SMOKE-001 — a real observer run writes heartbeat events that the
coach receive-side can observe.

SMOKE: no mocks. The real ``observer.cmd_run`` drives a real scan against
real runtime files; heartbeat events land in the worker's real
``events.jsonl``.

RED: ``cmd_run`` runs a real scan but emits no heartbeat event, so the
worker's ``events.jsonl`` stays empty and the coach sees no liveness.
"""
from __future__ import annotations

import json
from pathlib import Path

OBSERVER_ID = "tester-731-hbs-observer"
WORKER_ID = "tester-731-hbs"


def _heartbeat_events(runtime: Path, worker_id: str) -> list[dict]:
    path = runtime / "agents" / worker_id / "events.jsonl"
    if not path.exists():
        return []
    records = [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]
    return [r for r in records if r.get("event_type") == "heartbeat"]


def test_real_cmd_run_emits_heartbeat_events_for_the_worker(tmp_path):
    from atdd.coach.commands import observer

    runtime = tmp_path / "rt"
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()

    for _ in range(2):
        rc = observer.cmd_run(
            agent_id=OBSERVER_ID,
            runtime_dir=runtime,
            rules_dir=rules_dir,
            once=True,
        )
        assert rc == 0

    heartbeats = _heartbeat_events(runtime, WORKER_ID)
    assert len(heartbeats) >= 2, (
        "real observer run emitted no heartbeat events — coach RuntimeWatcher "
        "would report the worker as silent"
    )
