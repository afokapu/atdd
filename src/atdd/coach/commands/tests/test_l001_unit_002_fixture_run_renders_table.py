# URN: test:drive-state-machine:coach-state-machine-and-runtime:L001-UNIT-002-fixture-run-renders-table
# Acceptance: acc:drive-state-machine:L001-UNIT-002-fixture-run-renders-table
# WMBT: wmbt:drive-state-machine:L001
# Phase: RED
# Layer: application
# Assertion: behavioral
"""`atdd coach status` with a fixture run renders run-id, per-issue phase
from decisions, and recent decisions in a readable table.

Issue #616. Spec: issue body GT-002.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

_RUN_ID = "run-abc"


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _seed_decisions(runtime_dir: Path, run_id: str = _RUN_ID) -> None:
    coach_dir = runtime_dir / "coach"
    coach_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    records = [
        {
            "decision_id": "d-001",
            "timestamp": _iso(now - timedelta(minutes=10)),
            "coach_run_id": run_id,
            "issue_number": 616,
            "decision_type": "phase-transition",
            "inputs": {"from_phase": "INIT"},
            "outcome": {"to_phase": "PLANNED"},
        },
        {
            "decision_id": "d-002",
            "timestamp": _iso(now - timedelta(minutes=5)),
            "coach_run_id": run_id,
            "issue_number": 617,
            "decision_type": "phase-transition",
            "inputs": {"from_phase": "INIT"},
            "outcome": {"to_phase": "RED"},
        },
        {
            "decision_id": "d-003",
            "timestamp": _iso(now - timedelta(minutes=2)),
            "coach_run_id": run_id,
            "issue_number": 616,
            "decision_type": "agent-spawn",
            "inputs": {"persona": "tester"},
            "outcome": {"agent_id": "agent-616-tester"},
        },
    ]
    lines = "\n".join(json.dumps(r) for r in records) + "\n"
    (coach_dir / "decisions.jsonl").write_text(lines)


def test_status_renders_run_id(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    from atdd.coach.commands.coach import run_status

    runtime_dir = tmp_path / ".atdd" / "runtime"
    _seed_decisions(runtime_dir)

    rc = run_status([], runtime_dir=runtime_dir)
    out = capsys.readouterr().out

    assert rc == 0
    assert _RUN_ID in out


def test_status_renders_per_issue_phases(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    """Per-issue phase is derived from the latest phase-transition decision."""
    from atdd.coach.commands.coach import run_status

    runtime_dir = tmp_path / ".atdd" / "runtime"
    _seed_decisions(runtime_dir)

    run_status([], runtime_dir=runtime_dir)
    out = capsys.readouterr().out

    assert "616" in out
    assert "617" in out
    assert "PLANNED" in out
    assert "RED" in out


def test_status_renders_recent_decisions(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    """Recent decisions appear in the output."""
    from atdd.coach.commands.coach import run_status

    runtime_dir = tmp_path / ".atdd" / "runtime"
    _seed_decisions(runtime_dir)

    run_status([], runtime_dir=runtime_dir)
    out = capsys.readouterr().out

    # At least one decision type should appear
    assert "phase-transition" in out or "agent-spawn" in out


def test_status_decisions_flag_limits_count(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    """--decisions 1 limits output to last 1 decision."""
    from atdd.coach.commands.coach import run_status

    runtime_dir = tmp_path / ".atdd" / "runtime"
    _seed_decisions(runtime_dir)

    run_status(["--decisions", "1"], runtime_dir=runtime_dir)
    out = capsys.readouterr().out

    # d-003 is last, d-001 should NOT appear since we limit to 1
    assert "d-003" in out
    assert "d-001" not in out
