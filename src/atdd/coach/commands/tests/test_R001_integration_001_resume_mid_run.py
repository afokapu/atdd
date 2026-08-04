# URN: test:drive-state-machine:coach-state-machine-and-runtime:R001-INTEGRATION-001-resume-mid-run
# Acceptance: acc:drive-state-machine:R001-INTEGRATION-001-resume-mid-run
# WMBT: wmbt:drive-state-machine:R001
# Phase: RED
# Layer: integration
"""R001-INTEGRATION-001 — `atdd coach --resume <run-id>` reconstructs
per-issue state from `decisions.jsonl` and proceeds without
re-executing already-logged transitions.

Given a coach run killed after issue 358 reached PLANNED but before
RED, when `--resume <run-id>` is invoked, then coach reads the durable
log, recognizes #358 as PLANNED, skips the INIT → PLANNED transition
(idempotency from #498 / P001), and drives toward the next allowed
transition per the §4.1 state-transition table.
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


def test_resume_reconstructs_phase_from_decisions_jsonl(tmp_path):
    """The most-recent reached phase per issue is reconstructed from
    decisions.jsonl filtered by coach_run_id."""
    from atdd.coach.commands.durability import DecisionWriter
    from atdd.coach.commands.resume import reconstruct_state

    writer = DecisionWriter(runtime_dir=tmp_path)
    run_id = "run-r001-1"
    _seed_decision(writer, run_id=run_id, issue=358, src="INIT", dst="PLANNED",
                   ts="2026-05-09T13:00:00Z")
    # Decoy from a different run-id must be ignored.
    _seed_decision(writer, run_id="other-run", issue=358, src="PLANNED", dst="RED",
                   ts="2026-05-09T13:30:00Z")

    state = reconstruct_state(runtime_dir=tmp_path, run_id=run_id)
    assert state == {358: "PLANNED"}, (
        f"reconstruct_state must filter by coach_run_id and pick the most "
        f"recent target_phase per issue; got {state}"
    )


def test_resume_skips_already_logged_transitions(tmp_path):
    """When the resume runner walks the planned path, transitions whose
    decision_id already exists in the durable log are recognized as done
    (the consumer side of P001's idempotency contract) — the
    corresponding action handler is NOT re-invoked."""
    from atdd.coach.commands.durability import DecisionWriter
    from atdd.coach.commands.resume import ResumeRunner

    writer = DecisionWriter(runtime_dir=tmp_path)
    run_id = "run-r001-2"
    # Pre-seed: INIT → PLANNED already happened.
    _seed_decision(writer, run_id=run_id, issue=358, src="INIT", dst="PLANNED",
                   ts="2026-05-09T13:00:00Z")

    invoked: list[tuple[int, str, str]] = []

    def action(issue: int, src: str, dst: str) -> dict:
        invoked.append((issue, src, dst))
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

    # The INIT → PLANNED handler must NOT have been invoked (it was
    # already logged). PLANNED → RED → ... → COMPLETE handlers run.
    assert (358, "INIT", "PLANNED") not in invoked, (
        "already-logged transition was re-executed during resume"
    )
    # Forward progress: subsequent transitions were driven.
    assert (358, "PLANNED", "RED") in invoked, (
        f"resume runner must drive forward from reconstructed phase; "
        f"invoked={invoked}"
    )


def test_resume_run_completes_killed_issue(tmp_path):
    """End-to-end: a coach run killed at PLANNED reaches COMPLETE for
    the resumed issue without manual intervention."""
    from atdd.coach.commands.durability import DecisionWriter
    from atdd.coach.commands.resume import ResumeRunner

    writer = DecisionWriter(runtime_dir=tmp_path)
    run_id = "run-r001-3"
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
    final_phases = runner.drive_to_complete(issue_numbers=[358])

    assert final_phases.get(358) == "COMPLETE", (
        f"resumed issue must reach COMPLETE; got {final_phases}"
    )
