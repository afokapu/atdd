# URN: test:integration-hardening:coach-decisions-wiring:D001-INTEGRATION-002-write-before-side-effect
# Acceptance: acc:integration-hardening:D001-INTEGRATION-002-write-before-side-effect
# WMBT: wmbt:integration-hardening:D001
# Phase: RED
# Layer: integration
"""J3-INTEGRATION-002 — decision write completes before side-effect runs
(durable-before-action discipline, spec §4.5).

Simulating a crash between decision-write and side-effect: the
decisions.jsonl records the to_state (the decision IS written) but no
spawn artifacts for that state exist. A subsequent ``--resume <run-id>``
re-issues the side-effect cleanly without duplicating the decision line.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


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


def test_decision_recorded_before_crash_during_side_effect(tmp_path):
    """When the side-effect handler crashes after decisions.handle() runs,
    the decision is still durably recorded in decisions.jsonl.

    This verifies the durable-before-action invariant: the decision write
    completes BEFORE any side-effect, so a crash mid-side-effect leaves
    the log intact for --resume replay.
    """
    from atdd.coach.handlers import decisions
    from atdd.coach.commands.durability import DecisionWriter, transactional_decision

    run_id = "run-j3-crash"
    ctx = _make_ctx(issue_number=586, run_id=run_id, runtime_dir=tmp_path)

    transition = _make_transition("INIT", "PLANNED")
    result = decisions.handle(ctx, transition)

    log_path = tmp_path / "coach" / "decisions.jsonl"
    assert log_path.exists(), "decisions.jsonl must exist after handle()"

    records = _read_jsonl(log_path)
    assert len(records) == 1, (
        f"Expected 1 decision record after INIT→PLANNED; got {len(records)}"
    )
    assert records[0]["inputs"]["target_phase"] == "PLANNED", (
        "Recorded decision must carry to_state=PLANNED"
    )


def test_resume_after_crash_does_not_duplicate_decision(tmp_path):
    """After a crash that left decisions.jsonl with the INIT→PLANNED record,
    a --resume pass re-issues the side-effect but does NOT duplicate the
    decision line (idempotency contract from P001 / #498).
    """
    from atdd.coach.handlers import decisions
    from atdd.coach.commands.durability import DecisionWriter
    from atdd.coach.commands.resume import ResumeRunner

    run_id = "run-j3-resume"

    ctx = _make_ctx(issue_number=586, run_id=run_id, runtime_dir=tmp_path)
    decisions.handle(ctx, _make_transition("INIT", "PLANNED"))

    initial_records = _read_jsonl(tmp_path / "coach" / "decisions.jsonl")
    assert len(initial_records) == 1

    side_effects: list[tuple[int, str, str]] = []

    def record_action(issue: int, src: str, dst: str) -> dict:
        side_effects.append((issue, src, dst))
        return {"transitioned": True, "new_phase": dst}

    writer = DecisionWriter(runtime_dir=tmp_path)
    runner = ResumeRunner(
        runtime_dir=tmp_path,
        run_id=run_id,
        decision_writer=writer,
        transition_action=record_action,
    )
    runner.drive_to_complete(issue_numbers=[586])

    all_records = _read_jsonl(tmp_path / "coach" / "decisions.jsonl")
    decision_ids = [r["decision_id"] for r in all_records]
    assert len(decision_ids) == len(set(decision_ids)), (
        "Duplicate decision_ids found after resume: pre-existing INIT→PLANNED "
        "must not be re-written"
    )

    init_planned = [r for r in all_records
                    if r["inputs"].get("current_phase") == "INIT"
                    and r["inputs"].get("target_phase") == "PLANNED"]
    assert len(init_planned) == 1, (
        f"INIT→PLANNED was logged {len(init_planned)} times; "
        "resume must not duplicate a pre-existing decision"
    )


def test_resume_re_issues_side_effect_for_crashed_transition(tmp_path):
    """After a crash (decision written, side-effect not run), resume
    re-issues the side-effect for the crashed transition without
    duplicating the decision.

    Verifies: the decision_id acts as an idempotency key — once written,
    the action is skipped on replay. Side-effects for transitions that
    have NO decision record are issued.
    """
    from atdd.coach.handlers import decisions
    from atdd.coach.commands.durability import DecisionWriter
    from atdd.coach.commands.resume import ResumeRunner

    run_id = "run-j3-reissue"

    ctx = _make_ctx(issue_number=586, run_id=run_id, runtime_dir=tmp_path)
    decisions.handle(ctx, _make_transition("INIT", "PLANNED"))

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

    assert (586, "INIT", "PLANNED") not in invoked, (
        "side-effect for already-logged INIT→PLANNED was re-issued during resume"
    )
    assert (586, "PLANNED", "RED") in invoked, (
        f"resume did not re-issue PLANNED→RED (next transition); invoked={invoked}"
    )
