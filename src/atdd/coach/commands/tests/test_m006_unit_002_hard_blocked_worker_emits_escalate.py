# URN: test:observe-and-correct:worker-coach-event-loop:M006-UNIT-002-hard-blocked-worker-emits-escalate
# Acceptance: acc:observe-and-correct:M006-UNIT-002-hard-blocked-worker-emits-escalate
# WMBT: wmbt:observe-and-correct:M006
# Phase: RED
# Layer: application
"""M006-UNIT-002 — when the observer detects its worker is hard-blocked
or idle past the escalation threshold, it emits an ``atdd agent escalate``
record (into the worker's ``escalations.jsonl``).

RED: ``Observer.scan_once`` does no blocked detection, so a hard-blocked
worker produces no ``escalations.jsonl`` entry.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

OBSERVER_ID = "coder-731-blk2-observer"
WORKER_ID = "coder-731-blk2"


def _escalation_records(runtime: Path, worker_id: str) -> list[dict]:
    path = runtime / "agents" / worker_id / "escalations.jsonl"
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


def _idle_worker(runtime: Path, worker_id: str, idle_seconds: float) -> None:
    agent_dir = runtime / "agents" / worker_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    log = agent_dir / "output.log"
    log.write_text("worker has produced no output for a long time\n")
    stale = time.time() - idle_seconds
    os.utime(log, (stale, stale))


def _observer(runtime: Path, worktree: Path):
    from atdd.coach.commands.observer import Observer

    return Observer(
        agent_id=OBSERVER_ID, runtime_dir=runtime, rules_dir=None, worktree=worktree,
    )


def test_hard_blocked_worker_produces_an_escalation(tmp_path):
    runtime = tmp_path / "rt"
    worktree = tmp_path / "wt"
    worktree.mkdir()
    # Idle far past any reasonable escalation threshold.
    _idle_worker(runtime, WORKER_ID, idle_seconds=86_400)

    obs = _observer(runtime, worktree)
    obs.scan_once()

    escalations = _escalation_records(runtime, WORKER_ID)
    assert escalations, (
        "observer did not escalate a worker idle for a full day"
    )


def test_escalation_records_the_blocked_condition(tmp_path):
    runtime = tmp_path / "rt"
    worktree = tmp_path / "wt"
    worktree.mkdir()
    _idle_worker(runtime, WORKER_ID, idle_seconds=86_400)

    obs = _observer(runtime, worktree)
    obs.scan_once()

    escalations = _escalation_records(runtime, WORKER_ID)
    assert escalations, "no escalation emitted"
    record = escalations[0]
    assert record.get("reason"), "escalation record has no reason describing the block"
