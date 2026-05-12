# URN: test:drive-state-machine:coach-state-machine-and-runtime:L001-UNIT-003-json-flag-parseable
# Acceptance: acc:drive-state-machine:L001-UNIT-003-json-flag-parseable
# WMBT: wmbt:drive-state-machine:L001
# Phase: RED
# Layer: application
# Assertion: behavioral
"""`atdd coach status --json` emits machine-readable JSON with run_id,
issues, and decisions keys.

Issue #616. Spec: issue body GT-003.
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


def _seed_decisions(runtime_dir: Path) -> None:
    coach_dir = runtime_dir / "coach"
    coach_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    record = {
        "decision_id": "d-001",
        "timestamp": _iso(now - timedelta(minutes=5)),
        "coach_run_id": _RUN_ID,
        "issue_number": 616,
        "decision_type": "phase-transition",
        "inputs": {"from_phase": "INIT"},
        "outcome": {"to_phase": "PLANNED"},
    }
    (runtime_dir / "coach" / "decisions.jsonl").write_text(
        json.dumps(record) + "\n"
    )


def test_json_flag_emits_valid_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    from atdd.coach.commands.coach import run_status

    runtime_dir = tmp_path / ".atdd" / "runtime"
    _seed_decisions(runtime_dir)

    rc = run_status(["--json"], runtime_dir=runtime_dir)
    out = capsys.readouterr().out

    assert rc == 0
    parsed = json.loads(out)
    assert isinstance(parsed, dict)


def test_json_output_has_required_keys(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    from atdd.coach.commands.coach import run_status

    runtime_dir = tmp_path / ".atdd" / "runtime"
    _seed_decisions(runtime_dir)

    run_status(["--json"], runtime_dir=runtime_dir)
    out = capsys.readouterr().out

    parsed = json.loads(out)
    assert "run_id" in parsed
    assert "issues" in parsed
    assert "decisions" in parsed


def test_json_run_id_matches_fixture(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    from atdd.coach.commands.coach import run_status

    runtime_dir = tmp_path / ".atdd" / "runtime"
    _seed_decisions(runtime_dir)

    run_status(["--json"], runtime_dir=runtime_dir)
    out = capsys.readouterr().out

    parsed = json.loads(out)
    assert parsed["run_id"] == _RUN_ID


def test_json_issues_is_dict_keyed_by_issue_number(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    from atdd.coach.commands.coach import run_status

    runtime_dir = tmp_path / ".atdd" / "runtime"
    _seed_decisions(runtime_dir)

    run_status(["--json"], runtime_dir=runtime_dir)
    out = capsys.readouterr().out

    parsed = json.loads(out)
    assert isinstance(parsed["issues"], dict)
    assert "616" in parsed["issues"] or 616 in parsed["issues"]


def test_json_no_runs_outputs_valid_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    """--json with no runs should still emit valid JSON, not raise."""
    from atdd.coach.commands.coach import run_status

    runtime_dir = tmp_path / ".atdd" / "runtime"

    rc = run_status(["--json"], runtime_dir=runtime_dir)
    out = capsys.readouterr().out

    assert rc == 0
    parsed = json.loads(out)
    assert "run_id" in parsed
    assert parsed["run_id"] is None
