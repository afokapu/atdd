# URN: test:observe-and-correct:worker-coach-event-loop:M006-UNIT-003-healthy-worker-emits-no-ask-or-escalate
# Acceptance: acc:observe-and-correct:M006-UNIT-003-healthy-worker-emits-no-ask-or-escalate
# WMBT: wmbt:observe-and-correct:M006
# Phase: RED
# Layer: application
"""M006-UNIT-003 — a worker that is making progress triggers neither
``ask`` nor ``escalate``: the blocked detector must not false-positive on
a quiet-but-working worker.

This is the no-false-positive guard for M006-UNIT-001/002. It fails RED
because the detector does not exist yet — the file is anchored so the
acceptance has bidirectional binding; once the detector lands it must
keep this case silent.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

OBSERVER_ID = "coder-731-blk3-observer"
WORKER_ID = "coder-731-blk3"


def _records(runtime: Path, worker_id: str, filename: str) -> list[dict]:
    path = runtime / "agents" / worker_id / filename
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


def _healthy_worker(runtime: Path, worktree: Path, worker_id: str) -> None:
    """A worker producing fresh output and worktree changes right now."""
    agent_dir = runtime / "agents" / worker_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    log = agent_dir / "output.log"
    log.write_text("actively editing files and making progress\n")
    now = time.time()
    import os

    os.utime(log, (now, now))
    (worktree / "progress.py").write_text("# fresh work\n")


def _observe_twice(runtime: Path, worktree: Path):
    """Detector must stay silent across repeated scans of a healthy worker."""
    from atdd.coach.commands.observer import Observer

    obs = Observer(
        agent_id=OBSERVER_ID, runtime_dir=runtime, rules_dir=None, worktree=worktree,
    )
    obs.scan_once()
    # second scan: worker still progressing
    (worktree / "progress2.py").write_text("# more fresh work\n")
    obs.scan_once()


def test_healthy_worker_triggers_no_ask(tmp_path):
    runtime = tmp_path / "rt"
    worktree = tmp_path / "wt"
    worktree.mkdir()
    _healthy_worker(runtime, worktree, WORKER_ID)
    _observe_twice(runtime, worktree)

    # The acceptance demands a real, exercised blocked detector that stays
    # silent here. RED: no detector exists, so M006 is not yet satisfied.
    from atdd.coach.commands.observer import Observer

    assert hasattr(Observer, "detect_blocked_worker") or hasattr(
        Observer, "check_worker_progress"
    ), "no blocked-worker detector exists on Observer yet (M006 unimplemented)"
    assert _records(runtime, WORKER_ID, "questions.jsonl") == []


def test_healthy_worker_triggers_no_escalation(tmp_path):
    runtime = tmp_path / "rt"
    worktree = tmp_path / "wt"
    worktree.mkdir()
    _healthy_worker(runtime, worktree, WORKER_ID)
    _observe_twice(runtime, worktree)

    from atdd.coach.commands.observer import Observer

    assert hasattr(Observer, "detect_blocked_worker") or hasattr(
        Observer, "check_worker_progress"
    ), "no blocked-worker detector exists on Observer yet (M006 unimplemented)"
    assert _records(runtime, WORKER_ID, "escalations.jsonl") == []
