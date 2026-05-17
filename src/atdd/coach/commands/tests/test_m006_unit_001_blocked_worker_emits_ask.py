# URN: test:observe-and-correct:worker-coach-event-loop:M006-UNIT-001-blocked-worker-emits-ask
# Acceptance: acc:observe-and-correct:M006-UNIT-001-blocked-worker-emits-ask
# WMBT: wmbt:observe-and-correct:M006
# Phase: RED
# Layer: application
"""M006-UNIT-001 — when the observer detects its worker is blocked
awaiting a decision, it emits exactly one ``atdd agent ask`` record on
the worker's behalf (into the worker's ``questions.jsonl``).

Issue #731 Phase 2 — the worker LLM is not relied on to emit ``ask``;
the observer detects the blocked state and emits it.

RED: ``Observer.scan_once`` does no blocked detection, so a blocked
worker produces no ``questions.jsonl`` entry.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

OBSERVER_ID = "coder-731-blk1-observer"
WORKER_ID = "coder-731-blk1"


def _ask_records(runtime: Path, worker_id: str) -> list[dict]:
    path = runtime / "agents" / worker_id / "questions.jsonl"
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


def _blocked_worker(runtime: Path, worker_id: str, idle_seconds: float) -> None:
    """Create a worker whose output.log is stale by *idle_seconds* and
    carries a pending-decision marker — a worker stalled on a decision."""
    agent_dir = runtime / "agents" / worker_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    log = agent_dir / "output.log"
    log.write_text(
        "Considering the architecture...\n"
        "I need a decision: should the env injection live in the adapter "
        "or in cmd_spawn? I cannot proceed without an answer.\n"
    )
    stale = time.time() - idle_seconds
    os.utime(log, (stale, stale))


def _observer(runtime: Path, worktree: Path):
    from atdd.coach.commands.observer import Observer

    return Observer(
        agent_id=OBSERVER_ID, runtime_dir=runtime, rules_dir=None, worktree=worktree,
    )


def test_blocked_worker_produces_exactly_one_ask(tmp_path):
    runtime = tmp_path / "rt"
    worktree = tmp_path / "wt"
    worktree.mkdir()
    _blocked_worker(runtime, WORKER_ID, idle_seconds=3600)

    obs = _observer(runtime, worktree)
    obs.scan_once()

    asks = _ask_records(runtime, WORKER_ID)
    assert len(asks) == 1, (
        f"observer did not emit exactly one ask for a blocked worker: {asks!r}"
    )


def test_ask_carries_worker_id_and_decision_context(tmp_path):
    runtime = tmp_path / "rt"
    worktree = tmp_path / "wt"
    worktree.mkdir()
    _blocked_worker(runtime, WORKER_ID, idle_seconds=3600)

    obs = _observer(runtime, worktree)
    obs.scan_once()

    asks = _ask_records(runtime, WORKER_ID)
    assert asks, "no ask record emitted for a blocked worker"
    record = asks[0]
    # The ask lands under agents/<worker_id>/ and names a real question.
    assert (runtime / "agents" / WORKER_ID / "questions.jsonl").exists()
    assert record.get("question"), "ask record has no question text / decision context"
