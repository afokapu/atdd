# URN: test:integration-hardening:coach-resume-wiring:E009-UNIT-001-missing-transition-action-fails-loudly
# Acceptance: acc:integration-hardening:E009-UNIT-001-missing-transition-action-fails-loudly
# WMBT: wmbt:integration-hardening:E009
# Phase: RED
# Layer: unit
"""E009-UNIT-001 — ``ResumeRunner.drive_to_complete`` fails loudly when no
``transition_action`` is wired.

Today ``coach.py`` constructs ``ResumeRunner`` with no ``transition_action``,
so it defaults to ``None``; ``drive_to_complete`` then paper-walks every
pending phase to COMPLETE — no persona spawn, no tests, no orchestration
(observed live on #662: SMOKE→REFACTOR and REFACTOR→COMPLETE written 0.9 ms
apart). A resumed run with pending phases and ``transition_action=None`` must
instead raise a clear error *before* writing any phase-transition record — a
silent paper fast-forward is never a valid outcome.
"""
from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.platform]

RUN_ID = "coach-run-734-unit-001"


def _seed(writer, *, issue: int, src: str, dst: str, ts: str) -> None:
    writer.append({
        "decision_id": f"{RUN_ID}:#{issue}:{src}->{dst}",
        "timestamp": ts,
        "coach_run_id": RUN_ID,
        "issue_number": issue,
        "decision_type": "phase-transition",
        "inputs": {"current_phase": src, "target_phase": dst},
        "outcome": {"transitioned": True, "new_phase": dst},
    })


def _read_jsonl(path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_drive_to_complete_with_no_transition_action_raises(tmp_path):
    """transition_action=None on a mid-lifecycle issue raises a loud error
    naming the missing transition_action."""
    from atdd.coach.commands.durability import DecisionWriter
    from atdd.coach.commands.resume import ResumeRunner

    writer = DecisionWriter(runtime_dir=tmp_path)
    # Reconstruct issue 999 to SMOKE — pending phases (REFACTOR, COMPLETE) remain.
    _seed(writer, issue=999, src="INIT", dst="PLANNED", ts="2026-05-17T10:00:00Z")
    _seed(writer, issue=999, src="PLANNED", dst="RED", ts="2026-05-17T10:01:00Z")
    _seed(writer, issue=999, src="RED", dst="GREEN", ts="2026-05-17T10:02:00Z")
    _seed(writer, issue=999, src="GREEN", dst="SMOKE", ts="2026-05-17T10:03:00Z")

    runner = ResumeRunner(
        runtime_dir=tmp_path,
        run_id=RUN_ID,
        decision_writer=writer,
        transition_action=None,  # the current coach.py default
    )

    with pytest.raises((ValueError, RuntimeError)) as excinfo:
        runner.drive_to_complete(issue_numbers=[999])

    assert "transition_action" in str(excinfo.value), (
        f"the loud error must name the missing transition_action; "
        f"got: {excinfo.value!r}"
    )


def test_no_phase_transition_record_written_when_action_missing(tmp_path):
    """When drive_to_complete fails loudly it appends zero phase-transition
    records — no paper SMOKE→REFACTOR or REFACTOR→COMPLETE stamp."""
    from atdd.coach.commands.durability import DecisionWriter
    from atdd.coach.commands.resume import ResumeRunner

    writer = DecisionWriter(runtime_dir=tmp_path)
    _seed(writer, issue=999, src="GREEN", dst="SMOKE", ts="2026-05-17T10:03:00Z")

    before = len(_read_jsonl(writer.path))

    runner = ResumeRunner(
        runtime_dir=tmp_path,
        run_id=RUN_ID,
        decision_writer=writer,
        transition_action=None,
    )
    with pytest.raises((ValueError, RuntimeError)):
        runner.drive_to_complete(issue_numbers=[999])

    after = _read_jsonl(writer.path)
    assert len(after) == before, (
        f"drive_to_complete must append no records when it fails loudly; "
        f"{before} -> {len(after)} records"
    )
    targets = [(r.get("inputs") or {}).get("target_phase") for r in after]
    assert "REFACTOR" not in targets, "a SMOKE→REFACTOR record was paper-stamped"
    assert "COMPLETE" not in targets, "a REFACTOR→COMPLETE record was paper-stamped"
