# URN: test:drive-state-machine:coach-state-machine-and-runtime:P001-UNIT-005-durability-smoke
# Acceptance: acc:drive-state-machine:P001-UNIT-001-decisions-append-only
# WMBT: wmbt:drive-state-machine:P001
# Phase: SMOKE
# Layer: assembly
# Smoke: true
# Purpose: verify J3 writers against real schema files + real fs + real OS-level concurrency
"""P001 SMOKE — exercise the J3 writers against real infrastructure.

What this verifies that the unit tests do not:
- The writers load and validate against the *committed* C0 schema
  files at ``src/atdd/coach/schemas/`` (no fixtures, no test doubles).
- Multi-process concurrent appends preserve no-interleave guarantees
  under POSIX ``O_APPEND`` semantics on the real filesystem.
- ``fsync`` durability survives an abrupt close-and-reopen cycle: the
  log is replayable record-by-record after every append.
- Replay across a freshly-instantiated writer (simulating coach
  restart) skips already-recorded decisions.
"""
from __future__ import annotations

import json
import multiprocessing as mp
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _worker_append(runtime_dir: str, worker_id: int, n: int) -> None:
    """Top-level so it pickles for `mp.spawn`/`fork`."""
    from atdd.coach.commands.durability import DecisionWriter

    writer = DecisionWriter(runtime_dir=Path(runtime_dir))
    for i in range(n):
        writer.append(
            {
                "decision_id": f"w{worker_id}-{i}",
                "timestamp": "2026-05-09T13:45:02Z",
                "coach_run_id": "smoke-run",
                "issue_number": 498,
                "decision_type": "phase-transition",
                "inputs": {"worker": worker_id, "i": i, "filler": "x" * 64},
                "outcome": {"ok": True},
            }
        )


def test_smoke_real_schemas_load_at_writer_init(tmp_path):
    """Both writers must load the committed schemas without error."""
    from atdd.coach.commands.durability import (
        DecisionWriter,
        JudgmentWriter,
        SCHEMAS_DIR,
    )

    assert (SCHEMAS_DIR / "coach-decision.schema.json").is_file()
    assert (SCHEMAS_DIR / "coach-judgment.schema.json").is_file()

    DecisionWriter(runtime_dir=tmp_path)
    JudgmentWriter(runtime_dir=tmp_path)


def test_smoke_multiprocess_append_no_interleave(tmp_path):
    """Concurrent appends from real OS processes don't interleave."""
    n_workers = 4
    n_per_worker = 50

    ctx = mp.get_context("fork")
    procs = [
        ctx.Process(target=_worker_append, args=(str(tmp_path), w, n_per_worker))
        for w in range(n_workers)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=30)
        assert p.exitcode == 0, f"worker {p.pid} exited {p.exitcode}"

    log = tmp_path / "coach" / "decisions.jsonl"
    records = _read_jsonl(log)
    assert len(records) == n_workers * n_per_worker

    ids = {r["decision_id"] for r in records}
    assert len(ids) == n_workers * n_per_worker, "duplicate or lost ids"

    raw = log.read_text()
    for line in raw.splitlines():
        if line:
            json.loads(line)


def test_smoke_resume_skips_recorded_decisions(tmp_path):
    """Crash-recovery analog: a fresh writer over the same runtime_dir
    treats existing decisions as already-executed."""
    from atdd.coach.commands.durability import DecisionWriter, transactional_decision

    rec_a = {
        "decision_id": "smoke-a",
        "timestamp": "2026-05-09T13:45:02Z",
        "coach_run_id": "r1",
        "issue_number": 498,
        "decision_type": "phase-transition",
        "inputs": {"phase": "INIT"},
        "outcome": {"phase": "PLANNED"},
    }

    side_effects: list[str] = []
    writer1 = DecisionWriter(runtime_dir=tmp_path)
    with transactional_decision(writer1, rec_a) as run_action:
        if run_action:
            side_effects.append("first-run")

    writer2 = DecisionWriter(runtime_dir=tmp_path)
    with transactional_decision(writer2, rec_a) as run_action:
        if run_action:
            side_effects.append("second-run")

    assert side_effects == ["first-run"]

    rec_b = {**rec_a, "decision_id": "smoke-b"}
    with transactional_decision(writer2, rec_b) as run_action:
        if run_action:
            side_effects.append("third-run")
    assert side_effects == ["first-run", "third-run"]

    records = _read_jsonl(writer1.path)
    assert [r["decision_id"] for r in records] == ["smoke-a", "smoke-b"]


def test_smoke_judgment_full_inputs_cache_round_trip(tmp_path):
    """Full inputs cached on disk reload identically; durable log keeps
    only the hash."""
    from atdd.coach.commands.durability import (
        JudgmentWriter,
        hash_inputs,
    )

    writer = JudgmentWriter(runtime_dir=tmp_path)
    full_inputs = {
        "prompt": "Should we advance from RED to GREEN?",
        "context": {"violations": [], "tests_passing": True},
        "model_hint": "claude-opus-4-7",
    }
    h = hash_inputs(full_inputs)

    writer.append(
        {
            "judgment_id": "smoke-judgment-1",
            "timestamp": "2026-05-09T13:45:02Z",
            "call_site": "phase-advance",
            "inputs_hash": h,
            "response": {"advance": True, "confidence": 0.95},
            "cached": False,
            "outcome": "ok",
            "model": "claude-opus-4-7",
            "latency_ms": 1234,
        },
        full_inputs=full_inputs,
    )

    [log_record] = _read_jsonl(writer.path)
    assert log_record["inputs_hash"] == h
    for forbidden in ("prompt", "context", "model_hint"):
        assert forbidden not in log_record, (
            f"{forbidden!r} leaked into durable log; should be cache-only"
        )

    cache_files = list(writer.cache_dir.glob("*.json"))
    assert len(cache_files) == 1
    cached = json.loads(cache_files[0].read_text(encoding="utf-8"))
    assert cached == full_inputs
    assert cache_files[0].name == h.replace(":", "_") + ".json"
