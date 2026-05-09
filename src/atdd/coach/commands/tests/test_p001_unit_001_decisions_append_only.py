# URN: test:drive-state-machine:coach-state-machine-and-runtime:P001-UNIT-001-decisions-append-only
# Acceptance: acc:drive-state-machine:P001-UNIT-001-decisions-append-only
# WMBT: wmbt:drive-state-machine:P001
# Phase: RED
# Layer: application
"""P001-UNIT-001 — every state transition is appended to
``decisions.jsonl`` BEFORE the action runs.

Per spec §4.5: "every state transition appended to ``decisions.jsonl``
*before* the action runs." This is the load-bearing invariant for #J6
resume — if the durable log is the source of truth and the decision is
recorded before the action, then idempotent actions absorb replay.

Records conform to ``coach-decision.schema.json`` from #483.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_decisions_log_path_under_runtime_coach(tmp_path):
    from atdd.coach.commands.durability import DecisionWriter

    writer = DecisionWriter(runtime_dir=tmp_path)
    expected = tmp_path / "coach" / "decisions.jsonl"
    assert writer.path == expected
    assert writer.path.parent.is_dir()


def test_append_writes_one_jsonl_record_per_call(tmp_path):
    from atdd.coach.commands.durability import DecisionWriter

    writer = DecisionWriter(runtime_dir=tmp_path)
    record = {
        "decision_id": "01HW9P5C8K3D5R8X4M7VJZ4MZA",
        "timestamp": "2026-05-09T13:45:02.482Z",
        "coach_run_id": "run-test",
        "issue_number": 498,
        "decision_type": "phase-transition",
        "inputs": {"current_phase": "INIT", "target_phase": "PLANNED"},
        "outcome": {"transitioned": True, "new_phase": "PLANNED"},
    }
    writer.append(record)
    writer.append({**record, "decision_id": "01HW9P5C8K3D5R8X4M7VJZ4MZB"})

    records = _read_jsonl(writer.path)
    assert len(records) == 2
    assert records[0]["decision_id"] == "01HW9P5C8K3D5R8X4M7VJZ4MZA"
    assert records[1]["decision_id"] == "01HW9P5C8K3D5R8X4M7VJZ4MZB"


def test_append_does_not_seek_and_truncate(tmp_path):
    """Append-only invariant: a new writer opening over an existing file
    must not erase prior content."""
    from atdd.coach.commands.durability import DecisionWriter

    writer1 = DecisionWriter(runtime_dir=tmp_path)
    writer1.append(
        {
            "decision_id": "first",
            "timestamp": "2026-05-09T13:45:00Z",
            "coach_run_id": "r",
            "issue_number": 498,
            "decision_type": "phase-transition",
            "inputs": {},
            "outcome": {},
        }
    )

    writer2 = DecisionWriter(runtime_dir=tmp_path)
    writer2.append(
        {
            "decision_id": "second",
            "timestamp": "2026-05-09T13:45:01Z",
            "coach_run_id": "r",
            "issue_number": 498,
            "decision_type": "phase-transition",
            "inputs": {},
            "outcome": {},
        }
    )

    records = _read_jsonl(writer1.path)
    assert [r["decision_id"] for r in records] == ["first", "second"]


def test_decision_recorded_before_action_runs_under_failure(tmp_path):
    """Decision-precedes-action invariant: if the action raises, the
    decision is still durably recorded. Verified by injecting a failure
    at action-time and observing the decision in the log."""
    from atdd.coach.commands.durability import DecisionWriter, transactional_decision

    writer = DecisionWriter(runtime_dir=tmp_path)
    record = {
        "decision_id": "tx-1",
        "timestamp": "2026-05-09T13:45:02Z",
        "coach_run_id": "r",
        "issue_number": 498,
        "decision_type": "phase-transition",
        "inputs": {},
        "outcome": {},
    }

    class ActionFailed(RuntimeError):
        pass

    with pytest.raises(ActionFailed):
        with transactional_decision(writer, record) as run_action:
            assert run_action is True
            raise ActionFailed("simulated mid-action crash")

    records = _read_jsonl(writer.path)
    assert len(records) == 1
    assert records[0]["decision_id"] == "tx-1"


def test_required_fields_per_c0_schema(tmp_path):
    """Required fields per coach-decision.schema.json: decision_id,
    timestamp, coach_run_id, issue_number, decision_type, inputs,
    outcome."""
    from atdd.coach.commands.durability import DecisionWriter

    writer = DecisionWriter(runtime_dir=tmp_path)
    full = {
        "decision_id": "d1",
        "timestamp": "2026-05-09T13:45:02Z",
        "coach_run_id": "r",
        "issue_number": 498,
        "decision_type": "phase-transition",
        "inputs": {"k": "v"},
        "outcome": {"ok": True},
    }
    writer.append(full)

    [rec] = _read_jsonl(writer.path)
    for field in (
        "decision_id",
        "timestamp",
        "coach_run_id",
        "issue_number",
        "decision_type",
        "inputs",
        "outcome",
    ):
        assert field in rec, f"missing required field: {field}"


def test_concurrent_appends_do_not_corrupt_records(tmp_path):
    """O_APPEND semantics: concurrent writes from different threads
    don't interleave partial records."""
    import threading
    from atdd.coach.commands.durability import DecisionWriter

    writer = DecisionWriter(runtime_dir=tmp_path)
    n_threads = 8
    n_per_thread = 25

    def worker(tid: int) -> None:
        for i in range(n_per_thread):
            writer.append(
                {
                    "decision_id": f"t{tid}-{i}",
                    "timestamp": "2026-05-09T13:45:02Z",
                    "coach_run_id": "r",
                    "issue_number": 498,
                    "decision_type": "phase-transition",
                    "inputs": {"thread": tid, "i": i},
                    "outcome": {},
                }
            )

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    records = _read_jsonl(writer.path)
    assert len(records) == n_threads * n_per_thread
    ids = {r["decision_id"] for r in records}
    assert len(ids) == n_threads * n_per_thread
