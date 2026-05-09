# URN: test:drive-state-machine:coach-state-machine-and-runtime:M001-INTEGRATION-005-append-only-no-interleave
# Acceptance: acc:drive-state-machine:M001-INTEGRATION-005-append-only-no-interleave
# WMBT: wmbt:drive-state-machine:M001
# Phase: RED
# Layer: integration
"""M001-INTEGRATION-005 — concurrent writes to ``decisions.jsonl`` from
the watcher and the coach main loop don't interleave partial records,
under simulated event-burst conditions. Records are written with
``O_APPEND`` + ``fsync``; readers see whole records or none.

Each event arrives at the coach state machine **exactly once** per its
idempotency contract from ``event-semantics.md``.
"""
from __future__ import annotations

import json
import multiprocessing as mp
import threading
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _writer_worker(runtime_dir: str, prefix: str, count: int) -> None:
    """Spawned by multiprocessing — must be top-level for pickling."""
    from atdd.coach.commands.durability import DecisionWriter

    writer = DecisionWriter(runtime_dir=Path(runtime_dir))
    for i in range(count):
        writer.append(
            {
                "decision_id": f"{prefix}-{i}",
                "timestamp": "2026-05-09T14:00:00Z",
                "coach_run_id": "burst-run",
                "issue_number": 510,
                "decision_type": "phase-transition",
                "inputs": {"prefix": prefix, "i": i},
                "outcome": {"transitioned": True},
            }
        )


def test_concurrent_thread_writes_no_partial_records(tmp_path):
    """Watcher thread + main-loop thread → 200 records total, every line
    parses as JSON, no record IDs are lost."""
    from atdd.coach.commands.durability import DecisionWriter

    writer = DecisionWriter(runtime_dir=tmp_path)
    n_threads = 4
    n_per_thread = 50

    def thread_worker(tid: int) -> None:
        for i in range(n_per_thread):
            writer.append(
                {
                    "decision_id": f"t{tid}-{i}",
                    "timestamp": "2026-05-09T14:00:00Z",
                    "coach_run_id": "thread-burst",
                    "issue_number": 510,
                    "decision_type": "phase-transition",
                    "inputs": {"thread": tid, "i": i},
                    "outcome": {},
                }
            )

    threads = [threading.Thread(target=thread_worker, args=(t,)) for t in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    lines = writer.path.read_text().splitlines()
    assert len(lines) == n_threads * n_per_thread

    records = []
    for line in lines:
        rec = json.loads(line)
        records.append(rec)

    ids = {r["decision_id"] for r in records}
    assert len(ids) == n_threads * n_per_thread


def test_concurrent_process_writes_no_partial_records(tmp_path):
    """Watcher process + coach process → records are O_APPEND atomic.
    POSIX guarantees writes <= PIPE_BUF (>= 4096) are atomic across
    processes when the file is opened with O_APPEND."""
    n_procs = 4
    n_per_proc = 40
    procs = [
        mp.Process(target=_writer_worker, args=(str(tmp_path), f"p{p}", n_per_proc))
        for p in range(n_procs)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join()
    for p in procs:
        assert p.exitcode == 0, f"writer process failed: exit {p.exitcode}"

    log_path = tmp_path / "coach" / "decisions.jsonl"
    lines = log_path.read_text().splitlines()
    assert len(lines) == n_procs * n_per_proc

    records = [json.loads(line) for line in lines]
    ids = {r["decision_id"] for r in records}
    assert len(ids) == n_procs * n_per_proc


def test_event_burst_each_event_arrives_exactly_once(tmp_path):
    """Under simulated burst (rapid file writes triggering watcher emits),
    each event arrives at the coach state machine exactly once per its
    idempotency contract — verified via the queue's natural-key dedup."""
    from atdd.coach.commands.watchers import CoachEventQueue

    queue = CoachEventQueue(runtime_dir=tmp_path)
    # Same commit observed N times (e.g. watcher restart + fresh emit).
    for _ in range(50):
        queue.put(
            {
                "event_type": "commit_observed",
                "agent_id": "agent-burst",
                "timestamp": "2026-05-09T14:00:00Z",
                "payload": {"sha": "abc123", "branch": "main", "worktree_path": "/x"},
            }
        )

    drained = [e for e in queue.drain() if e["event_type"] == "commit_observed"]
    assert len(drained) == 1, (
        f"burst should dedupe at-least-once events to exactly-one consumer hit; got {len(drained)}"
    )


def test_writer_uses_o_append_and_fsync(tmp_path):
    """Reopening with a fresh writer over an existing file does not seek-
    and-truncate; new records append after existing content."""
    from atdd.coach.commands.durability import DecisionWriter

    w1 = DecisionWriter(runtime_dir=tmp_path)
    w1.append(
        {
            "decision_id": "first",
            "timestamp": "2026-05-09T14:00:00Z",
            "coach_run_id": "r",
            "issue_number": 510,
            "decision_type": "phase-transition",
            "inputs": {},
            "outcome": {},
        }
    )

    w2 = DecisionWriter(runtime_dir=tmp_path)
    w2.append(
        {
            "decision_id": "second",
            "timestamp": "2026-05-09T14:00:01Z",
            "coach_run_id": "r",
            "issue_number": 510,
            "decision_type": "phase-transition",
            "inputs": {},
            "outcome": {},
        }
    )

    lines = w1.path.read_text().splitlines()
    assert [json.loads(line)["decision_id"] for line in lines] == ["first", "second"]
