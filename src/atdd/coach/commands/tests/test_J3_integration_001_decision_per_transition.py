# URN: test:integration-hardening:coach-decisions-wiring:D001-INTEGRATION-001-decision-per-transition
# Acceptance: acc:integration-hardening:D001-INTEGRATION-001-decision-per-transition
# WMBT: wmbt:integration-hardening:D001
# Phase: RED
# Layer: integration
"""J3-INTEGRATION-001 — every state transition produces exactly one
decisions.jsonl entry conforming to coach-decision.schema.json.

A full coach run from INIT to MERGED (driven via the decisions handler)
produces exactly N entries where N == count of state transitions on the
planned path. Each entry validates against the schema and carries the
correct from/to state pair.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

PLANNED_PATH_TRANSITIONS = [
    ("INIT", "PLANNED"),
    ("PLANNED", "RED"),
    ("RED", "GREEN"),
    ("GREEN", "SMOKE"),
    ("SMOKE", "REFACTOR"),
    ("REFACTOR", "COMPLETE"),
    ("COMPLETE", "MERGED"),
]


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _make_ctx(issue_number: int, run_id: str, runtime_dir: Path):
    from atdd.coach.handlers.state_machine import CoachContext
    return CoachContext(
        issue_number=issue_number,
        coach_run_id=run_id,
        runtime_dir=runtime_dir,
    )


def _make_transition(src: str, dst: str):
    from atdd.coach.handlers.state_machine import Phase, Transition
    return Transition(src=Phase(src), dst=Phase(dst))


def test_full_run_produces_one_entry_per_transition(tmp_path):
    """decisions.handle() called once per transition produces N entries
    in decisions.jsonl where N == number of transitions on planned path."""
    from atdd.coach.handlers import decisions

    ctx = _make_ctx(issue_number=586, run_id="run-j3-001", runtime_dir=tmp_path)

    for src, dst in PLANNED_PATH_TRANSITIONS:
        result = decisions.handle(ctx, _make_transition(src, dst))
        from atdd.coach.handlers.state_machine import HandlerResult
        assert result in (HandlerResult.HANDLED, HandlerResult.NOOP), (
            f"handler returned {result!r} for {src}→{dst}"
        )

    log_path = tmp_path / "coach" / "decisions.jsonl"
    assert log_path.exists(), "decisions.jsonl must exist after transitions"

    records = _read_jsonl(log_path)
    assert len(records) == len(PLANNED_PATH_TRANSITIONS), (
        f"Expected {len(PLANNED_PATH_TRANSITIONS)} entries for {len(PLANNED_PATH_TRANSITIONS)} "
        f"transitions; got {len(records)}"
    )


def test_each_entry_carries_correct_from_to_state(tmp_path):
    """Each decisions.jsonl entry has the correct current_phase and
    target_phase matching the transition that produced it."""
    from atdd.coach.handlers import decisions

    ctx = _make_ctx(issue_number=586, run_id="run-j3-002", runtime_dir=tmp_path)

    for src, dst in PLANNED_PATH_TRANSITIONS:
        decisions.handle(ctx, _make_transition(src, dst))

    records = _read_jsonl(tmp_path / "coach" / "decisions.jsonl")
    for rec, (src, dst) in zip(records, PLANNED_PATH_TRANSITIONS):
        assert rec["inputs"]["current_phase"] == src, (
            f"current_phase mismatch: expected {src!r}, got {rec['inputs'].get('current_phase')!r}"
        )
        assert rec["inputs"]["target_phase"] == dst, (
            f"target_phase mismatch: expected {dst!r}, got {rec['inputs'].get('target_phase')!r}"
        )
        assert rec["outcome"]["new_phase"] == dst, (
            f"new_phase in outcome mismatch: expected {dst!r}, got {rec['outcome'].get('new_phase')!r}"
        )


def test_each_entry_validates_against_schema(tmp_path):
    """Every decisions.jsonl entry must conform to coach-decision.schema.json."""
    from atdd.coach.handlers import decisions
    from atdd.coach.commands.durability import _load_validator

    ctx = _make_ctx(issue_number=586, run_id="run-j3-003", runtime_dir=tmp_path)

    for src, dst in PLANNED_PATH_TRANSITIONS:
        decisions.handle(ctx, _make_transition(src, dst))

    validator = _load_validator("coach-decision.schema.json")
    records = _read_jsonl(tmp_path / "coach" / "decisions.jsonl")
    assert records, "decisions.jsonl must have entries"

    for i, rec in enumerate(records):
        errors = list(validator.iter_errors(rec))
        assert not errors, (
            f"Entry {i} fails schema: {[str(e.message) for e in errors]}"
        )


def test_each_entry_carries_run_id_and_issue_number(tmp_path):
    """Every entry must carry the coach_run_id and issue_number from the context."""
    from atdd.coach.handlers import decisions

    run_id = "run-j3-004"
    issue = 586
    ctx = _make_ctx(issue_number=issue, run_id=run_id, runtime_dir=tmp_path)

    for src, dst in PLANNED_PATH_TRANSITIONS:
        decisions.handle(ctx, _make_transition(src, dst))

    records = _read_jsonl(tmp_path / "coach" / "decisions.jsonl")
    for rec in records:
        assert rec["coach_run_id"] == run_id, (
            f"coach_run_id mismatch: {rec.get('coach_run_id')!r} != {run_id!r}"
        )
        assert rec["issue_number"] == issue, (
            f"issue_number mismatch: {rec.get('issue_number')!r} != {issue!r}"
        )


def test_decision_ids_are_unique_across_full_run(tmp_path):
    """All decision_ids in a full run must be unique (no duplicates)."""
    from atdd.coach.handlers import decisions

    ctx = _make_ctx(issue_number=586, run_id="run-j3-005", runtime_dir=tmp_path)

    for src, dst in PLANNED_PATH_TRANSITIONS:
        decisions.handle(ctx, _make_transition(src, dst))

    records = _read_jsonl(tmp_path / "coach" / "decisions.jsonl")
    ids = [r["decision_id"] for r in records]
    assert len(ids) == len(set(ids)), (
        f"Duplicate decision_ids found in decisions.jsonl: {ids}"
    )
