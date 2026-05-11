# URN: test:integration-hardening:coach-decisions-wiring:J3-INTEGRATION-003-resume-replays-correctly
# Acceptance: acc:integration-hardening:J3-INTEGRATION-003-resume-replays-correctly
# WMBT: wmbt:integration-hardening:J3
# Phase: RED
# Layer: integration
"""J3-INTEGRATION-003 — `atdd coach --resume <run-id>` reconstructs
per-issue state from decisions.jsonl and continues from the last recorded
to_state without duplicating entries.

Verifies that the J6 reader (ResumeRunner / reconstruct_state) correctly
consumes the decisions.jsonl produced by the J3 decisions handler.
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


def _drive_transitions_up_to(ctx, runtime_dir: Path, transitions: list[tuple[str, str]]) -> None:
    """Drive the decisions handler for a subset of the planned path."""
    from atdd.coach.handlers import decisions
    for src, dst in transitions:
        decisions.handle(ctx, _make_transition(src, dst))


def test_reconstruct_state_reads_j3_produced_decisions(tmp_path):
    """reconstruct_state (J6 reader) correctly reads decisions.jsonl
    produced by the J3 decisions handler and returns the last to_state
    for the issue.
    """
    from atdd.coach.commands.resume import reconstruct_state

    run_id = "run-j3r-001"
    ctx = _make_ctx(issue_number=586, run_id=run_id, runtime_dir=tmp_path)

    _drive_transitions_up_to(ctx, tmp_path, [
        ("INIT", "PLANNED"),
        ("PLANNED", "RED"),
    ])

    state = reconstruct_state(runtime_dir=tmp_path, run_id=run_id)
    assert state == {586: "RED"}, (
        f"reconstruct_state must return {{586: 'RED'}} after INIT→PLANNED→RED; "
        f"got {state}"
    )


def test_resume_continues_from_last_recorded_phase(tmp_path):
    """ResumeRunner continues from the last phase recorded by the J3
    handler, not from INIT. Transitions before the last logged one are
    skipped (idempotent replay).
    """
    from atdd.coach.commands.durability import DecisionWriter
    from atdd.coach.commands.resume import ResumeRunner

    run_id = "run-j3r-002"
    ctx = _make_ctx(issue_number=586, run_id=run_id, runtime_dir=tmp_path)

    _drive_transitions_up_to(ctx, tmp_path, [
        ("INIT", "PLANNED"),
        ("PLANNED", "RED"),
        ("RED", "GREEN"),
    ])

    invoked: list[tuple[int, str, str]] = []

    def action(issue: int, src: str, dst: str) -> dict:
        invoked.append((issue, src, dst))
        return {"transitioned": True, "new_phase": dst}

    writer = DecisionWriter(runtime_dir=tmp_path)
    runner = ResumeRunner(
        runtime_dir=tmp_path,
        run_id=run_id,
        decision_writer=writer,
        transition_action=action,
    )
    runner.drive_to_complete(issue_numbers=[586])

    for already_done in [("INIT", "PLANNED"), ("PLANNED", "RED"), ("RED", "GREEN")]:
        src, dst = already_done
        assert (586, src, dst) not in invoked, (
            f"already-logged {src}→{dst} was re-issued during resume; "
            f"invoked={invoked}"
        )

    assert (586, "GREEN", "SMOKE") in invoked, (
        f"resume did not continue from GREEN to SMOKE; invoked={invoked}"
    )


def test_full_run_then_resume_from_mid_point_reaches_complete(tmp_path):
    """If a coach run was interrupted at RED, the resume pass drives it
    to COMPLETE. The final decisions.jsonl has exactly one entry per
    transition with no duplicates.
    """
    from atdd.coach.commands.durability import DecisionWriter
    from atdd.coach.commands.resume import ResumeRunner

    run_id = "run-j3r-003"
    ctx = _make_ctx(issue_number=586, run_id=run_id, runtime_dir=tmp_path)

    _drive_transitions_up_to(ctx, tmp_path, [
        ("INIT", "PLANNED"),
        ("PLANNED", "RED"),
    ])

    def action(issue: int, src: str, dst: str) -> dict:
        return {"transitioned": True, "new_phase": dst}

    writer = DecisionWriter(runtime_dir=tmp_path)
    runner = ResumeRunner(
        runtime_dir=tmp_path,
        run_id=run_id,
        decision_writer=writer,
        transition_action=action,
    )
    final = runner.drive_to_complete(issue_numbers=[586])

    assert final.get(586) == "COMPLETE", (
        f"resume must drive to COMPLETE; got {final}"
    )

    records = _read_jsonl(tmp_path / "coach" / "decisions.jsonl")
    ids = [r["decision_id"] for r in records]
    assert len(ids) == len(set(ids)), (
        "Duplicate decision_ids after combined original + resume run"
    )


def test_multiple_issues_reconstructed_independently(tmp_path):
    """When multiple issues share a coach_run_id, reconstruct_state
    returns the correct last phase for each issue independently.
    """
    from atdd.coach.commands.resume import reconstruct_state

    run_id = "run-j3r-multi"

    ctx_a = _make_ctx(issue_number=586, run_id=run_id, runtime_dir=tmp_path)
    ctx_b = _make_ctx(issue_number=587, run_id=run_id, runtime_dir=tmp_path)

    _drive_transitions_up_to(ctx_a, tmp_path, [
        ("INIT", "PLANNED"),
        ("PLANNED", "RED"),
    ])
    _drive_transitions_up_to(ctx_b, tmp_path, [
        ("INIT", "PLANNED"),
    ])

    state = reconstruct_state(runtime_dir=tmp_path, run_id=run_id)
    assert state.get(586) == "RED", (
        f"issue 586 must be at RED; got {state.get(586)!r}"
    )
    assert state.get(587) == "PLANNED", (
        f"issue 587 must be at PLANNED; got {state.get(587)!r}"
    )
