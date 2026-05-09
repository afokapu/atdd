# URN: test:drive-state-machine:coach-state-machine-and-runtime:R001-SMOKE-001-resume-real-runtime
# Acceptance: acc:drive-state-machine:R001-INTEGRATION-001-resume-mid-run
# WMBT: wmbt:drive-state-machine:R001
# Phase: SMOKE
# Layer: assembly
# Smoke: true
# Purpose: exercise the J6 resume runner against the real runtime layout
"""R001 SMOKE — exercise ``ResumeRunner`` against the real runtime
layout and the committed C0 schemas.

What this verifies that the integration tests do not:
- The runner reads ``decisions.jsonl`` written by the *real* J3
  ``DecisionWriter`` against the *committed* C0 schemas (no fixtures).
- The kill-and-resume cycle is end-to-end durable on the real
  filesystem: a first run logs INIT → PLANNED, the writer is closed,
  a fresh ``ResumeRunner`` is constructed, and forward progress
  reaches COMPLETE without re-executing any logged transition.
- Watcher reattachment uses the real ``runtime/agents/<id>/`` layout
  per ``runtime-layout.md`` and the natural-key dedup in the real
  ``CoachEventQueue``.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_smoke_kill_and_resume_end_to_end_on_real_fs(tmp_path):
    """End-to-end kill-and-resume on the real filesystem."""
    from atdd.coach.commands.durability import DecisionWriter
    from atdd.coach.commands.resume import ResumeRunner

    runtime = tmp_path / ".atdd" / "runtime"

    # ----- "Original" run: INIT → PLANNED then process killed.
    writer = DecisionWriter(runtime_dir=runtime)
    run_id = "smoke-run-r001"
    writer.append({
        "decision_id": f"{run_id}:#358:INIT->PLANNED",
        "timestamp": "2026-05-09T13:00:00Z",
        "coach_run_id": run_id,
        "issue_number": 358,
        "decision_type": "phase-transition",
        "inputs": {"current_phase": "INIT", "target_phase": "PLANNED"},
        "outcome": {"transitioned": True, "new_phase": "PLANNED"},
    })
    # Drop the writer instance to mimic process death.
    del writer

    # ----- Resumed run: fresh writer + runner, no in-memory continuity.
    writer2 = DecisionWriter(runtime_dir=runtime)
    actions: list[tuple[int, str, str]] = []

    def action(issue: int, src: str, dst: str) -> dict:
        actions.append((issue, src, dst))
        return {"transitioned": True, "new_phase": dst}

    runner = ResumeRunner(
        runtime_dir=runtime,
        run_id=run_id,
        decision_writer=writer2,
        transition_action=action,
    )
    final = runner.drive_to_complete([358])

    assert final[358] == "COMPLETE"
    # No re-execution of the already-logged INIT → PLANNED.
    assert (358, "INIT", "PLANNED") not in actions
    # Forward progress was driven through every PLANNED-path step.
    expected_path = [
        (358, "PLANNED", "RED"),
        (358, "RED", "GREEN"),
        (358, "GREEN", "SMOKE"),
        (358, "SMOKE", "REFACTOR"),
        (358, "REFACTOR", "COMPLETE"),
    ]
    assert actions == expected_path, (
        f"resume must drive PLANNED → COMPLETE step by step; got {actions}"
    )

    records = _read_jsonl(runtime / "coach" / "decisions.jsonl")
    decision_ids = [r["decision_id"] for r in records]
    assert len(decision_ids) == len(set(decision_ids)), (
        "no duplicate decision_ids on the real fs after resume"
    )


def test_smoke_watcher_reattach_against_real_runtime_layout(tmp_path):
    """Watcher reattaches against the real ``agents/<id>/`` layout."""
    from atdd.coach.commands.durability import DecisionWriter
    from atdd.coach.commands.resume import ResumeRunner

    runtime = tmp_path / ".atdd" / "runtime"
    agent_dir = runtime / "agents" / "smoke-agent"
    agent_dir.mkdir(parents=True, exist_ok=True)

    events_path = agent_dir / "events.jsonl"
    with events_path.open("w") as fh:
        fh.write(json.dumps({
            "event_type": "commit_observed",
            "agent_id": "smoke-agent",
            "timestamp": "2026-05-09T14:00:00Z",
            "payload": {"sha": "smoke-sha", "branch": "feat/smoke",
                        "worktree_path": "/x"},
        }) + "\n")

    writer = DecisionWriter(runtime_dir=runtime)
    runner = ResumeRunner(
        runtime_dir=runtime,
        run_id="smoke-watcher-r001",
        decision_writer=writer,
    )
    queue, watcher = runner.attach_watchers()
    try:
        events = queue.drain()
        commit_events = [e for e in events if e["event_type"] == "commit_observed"]
        assert len(commit_events) == 1
        assert commit_events[0]["payload"]["sha"] == "smoke-sha"

        # The runtime watcher's checkpoint file lives at
        # runtime/coach/watcher-checkpoint.json per
        # runtime-watcher.persist_checkpoint(). Verify it is on disk
        # after attach_watchers() so a subsequent restart picks it up.
        checkpoint = runtime / "coach" / "watcher-checkpoint.json"
        assert checkpoint.exists(), (
            "attach_watchers() must persist the watcher checkpoint to "
            "the real runtime/coach/ tree"
        )
    finally:
        watcher.stop()
