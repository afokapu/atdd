# URN: test:observe-and-correct:worker-coach-event-loop:M006-SMOKE-001-real-blocked-worker-reaches-coach
# Acceptance: acc:observe-and-correct:M006-SMOKE-001-real-blocked-worker-reaches-coach
# WMBT: wmbt:observe-and-correct:M006
# Phase: SMOKE
# Layer: integration
# Harness: smoke/backend
"""M006-SMOKE-001 — a real observer run on a genuinely blocked worker
emits ask/escalate records the coach receive-side can observe.

SMOKE: no mocks. The real ``observer.cmd_run`` scans a real worker whose
output stream has been stale for a full day; the ask lands in real
``questions.jsonl`` and the escalation in real ``escalations.jsonl``.

RED: ``cmd_run`` runs a real scan but does no blocked detection, so
neither file is written.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

OBSERVER_ID = "coder-731-blks-observer"
WORKER_ID = "coder-731-blks"


def _records(runtime: Path, worker_id: str, filename: str) -> list[dict]:
    path = runtime / "agents" / worker_id / filename
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


def test_real_cmd_run_surfaces_a_blocked_worker(tmp_path):
    from atdd.coach.commands import observer

    runtime = tmp_path / "rt"
    worktree = tmp_path / "wt"
    worktree.mkdir()
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()

    # A genuinely blocked worker: output stream stale for a full day.
    agent_dir = runtime / "agents" / WORKER_ID
    agent_dir.mkdir(parents=True)
    log = agent_dir / "output.log"
    log.write_text(
        "I need a decision before I can continue — blocked.\n"
    )
    stale = time.time() - 86_400
    os.utime(log, (stale, stale))

    rc = observer.cmd_run(
        agent_id=OBSERVER_ID,
        runtime_dir=runtime,
        rules_dir=rules_dir,
        worktree=worktree,
        once=True,
    )
    assert rc == 0

    asks = _records(runtime, WORKER_ID, "questions.jsonl")
    escalations = _records(runtime, WORKER_ID, "escalations.jsonl")
    assert asks, "real observer run emitted no ask for a day-idle worker"
    assert escalations, "real observer run emitted no escalation for a day-idle worker"
