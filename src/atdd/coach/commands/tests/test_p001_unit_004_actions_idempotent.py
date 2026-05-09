# URN: test:drive-state-machine:coach-state-machine-and-runtime:P001-UNIT-004-actions-idempotent
# Acceptance: acc:drive-state-machine:P001-UNIT-004-actions-idempotent
# WMBT: wmbt:drive-state-machine:P001
# Phase: RED
# Layer: application
"""P001-UNIT-004 — replaying a recorded transition skips the action.

Idempotency is the contract that makes #J6 resume feasible: replaying a
durable decision must NOT cause double-execution. The
``transactional_decision`` context manager checks the durable log for an
existing ``decision_id``; if found, the action body is skipped (the
context yields ``False``) and no new record is appended.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _make_record(decision_id: str = "init-planned-498") -> dict:
    return {
        "decision_id": decision_id,
        "timestamp": "2026-05-09T13:45:02Z",
        "coach_run_id": "r",
        "issue_number": 358,
        "decision_type": "phase-transition",
        "inputs": {"current_phase": "INIT", "target_phase": "PLANNED"},
        "outcome": {"transitioned": True, "new_phase": "PLANNED"},
    }


def test_has_decision_returns_false_on_empty_log(tmp_path):
    from atdd.coach.commands.durability import DecisionWriter

    writer = DecisionWriter(runtime_dir=tmp_path)
    assert writer.has_decision("any-id") is False


def test_has_decision_returns_true_after_append(tmp_path):
    from atdd.coach.commands.durability import DecisionWriter

    writer = DecisionWriter(runtime_dir=tmp_path)
    record = _make_record("d1")
    writer.append(record)
    assert writer.has_decision("d1") is True
    assert writer.has_decision("d2") is False


def test_replay_skips_action_and_does_not_double_log(tmp_path):
    """Replaying a recorded INIT→PLANNED transition for an issue causes
    the action to be recognized as already executed and skipped — no
    duplicate side-effects."""
    from atdd.coach.commands.durability import DecisionWriter, transactional_decision

    writer = DecisionWriter(runtime_dir=tmp_path)
    record = _make_record("init-planned-358")

    side_effects: list[str] = []

    with transactional_decision(writer, record) as run_action:
        assert run_action is True
        side_effects.append("commit")

    assert side_effects == ["commit"]
    assert len(_read_jsonl(writer.path)) == 1

    writer2 = DecisionWriter(runtime_dir=tmp_path)
    with transactional_decision(writer2, record) as run_action:
        assert run_action is False
        if run_action:  # pragma: no cover — guarded by run_action
            side_effects.append("commit-2")

    assert side_effects == ["commit"], "no duplicate side effect"
    assert len(_read_jsonl(writer2.path)) == 1, "no duplicate log entry"


def test_replay_with_different_decision_id_runs_action(tmp_path):
    """Sanity: a different decision_id is treated as new work."""
    from atdd.coach.commands.durability import DecisionWriter, transactional_decision

    writer = DecisionWriter(runtime_dir=tmp_path)
    writer.append(_make_record("first"))

    side_effects: list[str] = []
    with transactional_decision(writer, _make_record("second")) as run_action:
        assert run_action is True
        side_effects.append("ran")

    assert side_effects == ["ran"]
    assert len(_read_jsonl(writer.path)) == 2
