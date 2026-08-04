# URN: test:drive-state-machine:coach-state-machine-and-runtime:R001-INTEGRATION-002-no-duplicate-transitions
# Acceptance: acc:drive-state-machine:R001-INTEGRATION-002-no-duplicate-transitions
# WMBT: wmbt:drive-state-machine:R001
# Phase: RED
# Layer: integration
"""R001-INTEGRATION-002 — Resume does not write duplicate transitions
to ``decisions.jsonl``.

The action-precedes-write invariant from #498 / P001 holds; the resume
logic prevents re-execution upstream so duplicates never reach the
writer. The log contains each transition exactly once across the
original and resumed runs.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

# #1619: the resume walk now consults the enforcing transition gate, and
# PLANNED->RED is gated by DEFAULT_GATED_TRANSITIONS. These tests are about
# resume DURABILITY and idempotency, not about gates, so they declare their gate
# posture explicitly rather than depending on whatever config the cwd happens to
# carry. Pinning `worktree` to the test's own tmp tree matters just as much: left
# to its default the token lookup resolves up to the REAL shared Control Root.
_UNGATED_FOR_DURABILITY = {"gate": {"transitions": {"PLANNED->RED": False}}}



def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _seed_decision(writer, *, run_id: str, issue: int, src: str, dst: str, ts: str) -> None:
    writer.append({
        "decision_id": f"{run_id}:#{issue}:{src}->{dst}",
        "timestamp": ts,
        "coach_run_id": run_id,
        "issue_number": issue,
        "decision_type": "phase-transition",
        "inputs": {"current_phase": src, "target_phase": dst},
        "outcome": {"transitioned": True, "new_phase": dst},
    })


def test_no_duplicate_decisions_after_resume(tmp_path):
    """Pre-seeded transitions are not duplicated by the resumed run.

    Original run logs INIT → PLANNED. Resume drives the issue forward to
    COMPLETE. The final log contains each transition exactly once.
    """
    from atdd.coach.commands.durability import DecisionWriter
    from atdd.coach.commands.resume import ResumeRunner

    writer = DecisionWriter(runtime_dir=tmp_path)
    run_id = "run-r001-dup"
    _seed_decision(writer, run_id=run_id, issue=358, src="INIT", dst="PLANNED",
                   ts="2026-05-09T13:00:00Z")

    def action(issue: int, src: str, dst: str) -> dict:
        return {"transitioned": True, "new_phase": dst}

    runner = ResumeRunner(
        runtime_dir=tmp_path,
        worktree=tmp_path,
        gate_config=_UNGATED_FOR_DURABILITY,
        run_id=run_id,
        decision_writer=writer,
        transition_action=action,
    )
    runner.drive_to_complete(issue_numbers=[358])

    records = _read_jsonl(writer.path)
    decision_ids = [r["decision_id"] for r in records]
    assert len(decision_ids) == len(set(decision_ids)), (
        f"decisions.jsonl contains duplicate decision_ids after resume; "
        f"got {decision_ids}"
    )

    init_planned = [r for r in records
                    if r["inputs"].get("current_phase") == "INIT"
                    and r["inputs"].get("target_phase") == "PLANNED"]
    assert len(init_planned) == 1, (
        f"INIT → PLANNED was logged {len(init_planned)} times; resume "
        f"re-executed an already-logged transition"
    )


def test_resume_reaches_complete_for_resumed_issue(tmp_path):
    """The resumed issue reaches the COMPLETE phase exactly once in
    the durable log."""
    from atdd.coach.commands.durability import DecisionWriter
    from atdd.coach.commands.resume import ResumeRunner

    writer = DecisionWriter(runtime_dir=tmp_path)
    run_id = "run-r001-complete"
    _seed_decision(writer, run_id=run_id, issue=358, src="INIT", dst="PLANNED",
                   ts="2026-05-09T13:00:00Z")
    _seed_decision(writer, run_id=run_id, issue=358, src="PLANNED", dst="RED",
                   ts="2026-05-09T13:30:00Z")

    def action(issue: int, src: str, dst: str) -> dict:
        return {"transitioned": True, "new_phase": dst}

    runner = ResumeRunner(
        runtime_dir=tmp_path,
        worktree=tmp_path,
        gate_config=_UNGATED_FOR_DURABILITY,
        run_id=run_id,
        decision_writer=writer,
        transition_action=action,
    )
    runner.drive_to_complete(issue_numbers=[358])

    records = _read_jsonl(writer.path)
    completes = [r for r in records
                 if r["inputs"].get("target_phase") == "COMPLETE"]
    assert len(completes) == 1, (
        f"COMPLETE transition was logged {len(completes)} times; "
        f"resume must produce exactly one COMPLETE entry"
    )
