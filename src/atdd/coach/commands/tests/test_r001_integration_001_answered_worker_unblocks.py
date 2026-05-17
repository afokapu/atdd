# URN: test:observe-and-correct:worker-coach-event-loop:R001-INTEGRATION-001-answered-worker-unblocks
# Acceptance: acc:observe-and-correct:R001-INTEGRATION-001-answered-worker-unblocks
# WMBT: wmbt:observe-and-correct:R001
# Phase: RED
# Layer: integration
"""R001-INTEGRATION-001 — a blocked worker that emitted ``ask``, once its
answer is delivered, leaves the blocked state: the observer stops
escalating that same block.

RED: with no ``deliver_answer`` surface the answer cannot round-trip, so
this exercise cannot run to its assertion.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

OBSERVER_ID = "coder-731-ans3-observer"
WORKER_ID = "coder-731-ans3"


def _records(runtime: Path, worker_id: str, filename: str) -> list[dict]:
    path = runtime / "agents" / worker_id / filename
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


def _blocked_worker(runtime: Path, worker_id: str) -> None:
    agent_dir = runtime / "agents" / worker_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    log = agent_dir / "output.log"
    log.write_text("blocked: I need a decision to continue\n")
    stale = time.time() - 86_400
    os.utime(log, (stale, stale))


def test_answer_delivery_clears_the_blocked_state(tmp_path):
    from atdd.coach.commands import agent
    from atdd.coach.commands.observer import Observer

    runtime = tmp_path / "rt"
    worktree = tmp_path / "wt"
    worktree.mkdir()
    _blocked_worker(runtime, WORKER_ID)

    obs = Observer(
        agent_id=OBSERVER_ID, runtime_dir=runtime, rules_dir=None, worktree=worktree,
    )

    # First scan: the observer detects the block and asks on the worker's behalf.
    obs.scan_once()
    asks = _records(runtime, WORKER_ID, "questions.jsonl")
    assert asks, "blocked worker produced no ask to answer"
    question_id = asks[0]["question_id"]

    # The coach answers; the observer round-trips it back into the worker.
    obs.deliver_answer(question_id, "Proceed with approach A.")

    escalations_before = len(_records(runtime, WORKER_ID, "escalations.jsonl"))

    # A worker that received its answer is no longer blocked: simulate it
    # resuming (fresh output) and re-scan.
    log = runtime / "agents" / WORKER_ID / "output.log"
    log.write_text(log.read_text() + "resumed after answer\n")
    now = time.time()
    os.utime(log, (now, now))
    obs.scan_once()

    escalations_after = len(_records(runtime, WORKER_ID, "escalations.jsonl"))
    assert escalations_after == escalations_before, (
        "observer kept escalating a worker whose ask was already answered"
    )
