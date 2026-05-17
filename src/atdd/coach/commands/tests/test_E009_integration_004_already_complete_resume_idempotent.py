# URN: test:integration-hardening:coach-resume-wiring:E009-INTEGRATION-004-already-complete-resume-idempotent
# Acceptance: acc:integration-hardening:E009-INTEGRATION-004-already-complete-resume-idempotent
# WMBT: wmbt:integration-hardening:E009
# Phase: RED
# Layer: integration
"""E009-INTEGRATION-004 — resuming a run whose issue is already COMPLETE is
idempotent: no orchestration, no new records.

When the reconstructed phase is COMPLETE there are no pending transitions.
The wired ``transition_action`` must be invoked exactly zero times, no new
``phase-transition`` record is appended, and the resume run returns success.
This test injects a recording fake transition_action through the coach.py
resume path; it fails today because that path offers no injection point.
"""
from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.platform]

RUN_ID = "coach-run-734-int-004"


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


def test_resume_of_already_complete_issue_is_idempotent(tmp_path):
    """An issue reconstructed to COMPLETE drives no transitions and writes
    no new records — transition_action invoked exactly zero times."""
    from atdd.coach.commands.coach import run
    from atdd.coach.commands.durability import DecisionWriter

    runtime_dir = tmp_path / ".atdd" / "runtime"
    writer = DecisionWriter(runtime_dir=runtime_dir)
    # Reconstruct issue 999 all the way to COMPLETE — no pending phases.
    _seed(writer, issue=999, src="INIT", dst="PLANNED", ts="2026-05-17T10:00:00Z")
    _seed(writer, issue=999, src="PLANNED", dst="RED", ts="2026-05-17T10:01:00Z")
    _seed(writer, issue=999, src="RED", dst="GREEN", ts="2026-05-17T10:02:00Z")
    _seed(writer, issue=999, src="GREEN", dst="SMOKE", ts="2026-05-17T10:03:00Z")
    _seed(writer, issue=999, src="SMOKE", dst="REFACTOR", ts="2026-05-17T10:04:00Z")
    _seed(writer, issue=999, src="REFACTOR", dst="COMPLETE", ts="2026-05-17T10:05:00Z")

    before = _read_jsonl(writer.path)

    recorded: list[tuple[int, str, str]] = []

    def recording_action(issue: int, src: str, dst: str) -> dict:
        recorded.append((issue, src, dst))
        return {"transitioned": True, "new_phase": dst}

    rc = run(
        issue_numbers=[999],
        dry_run=False,
        resume=RUN_ID,
        _runtime_dir_override=runtime_dir,
        _transition_action_override=recording_action,
    )

    assert rc == 0, f"resuming an already-COMPLETE issue must succeed; rc={rc}"
    assert recorded == [], (
        f"transition_action must be invoked zero times for an already-COMPLETE "
        f"issue; got {recorded}"
    )

    after = _read_jsonl(writer.path)
    assert len(after) == len(before), (
        f"no new phase-transition record may be appended on an idempotent "
        f"resume; {len(before)} -> {len(after)} records"
    )
