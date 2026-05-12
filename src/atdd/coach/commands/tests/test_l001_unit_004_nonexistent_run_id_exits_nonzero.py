# URN: test:drive-state-machine:coach-state-machine-and-runtime:L001-UNIT-004-nonexistent-run-id-exits-nonzero
# Acceptance: acc:drive-state-machine:L001-UNIT-004-nonexistent-run-id-exits-nonzero
# WMBT: wmbt:drive-state-machine:L001
# Phase: RED
# Layer: application
# Assertion: behavioral
"""`atdd coach status --run-id nonexistent` exits non-zero with a clear
error message that names the requested run-id.

Issue #616. Spec: issue body GT-004.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _seed_decisions(runtime_dir: Path, run_id: str = "run-abc") -> None:
    coach_dir = runtime_dir / "coach"
    coach_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    record = {
        "decision_id": "d-001",
        "timestamp": _iso(now - timedelta(minutes=5)),
        "coach_run_id": run_id,
        "issue_number": 616,
        "decision_type": "phase-transition",
        "inputs": {"from_phase": "INIT"},
        "outcome": {"to_phase": "PLANNED"},
    }
    (runtime_dir / "coach" / "decisions.jsonl").write_text(
        json.dumps(record) + "\n"
    )


def test_nonexistent_run_id_exits_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    from atdd.coach.commands.coach import run_status

    runtime_dir = tmp_path / ".atdd" / "runtime"
    _seed_decisions(runtime_dir)  # run-abc exists

    rc = run_status(["--run-id", "run-xyz"], runtime_dir=runtime_dir)

    assert rc != 0


def test_nonexistent_run_id_error_names_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    """stderr should mention the requested run-id."""
    from atdd.coach.commands.coach import run_status

    runtime_dir = tmp_path / ".atdd" / "runtime"
    _seed_decisions(runtime_dir)

    run_status(["--run-id", "run-xyz"], runtime_dir=runtime_dir)
    err = capsys.readouterr().err

    assert "run-xyz" in err


def test_nonexistent_run_id_no_runtime_dir_exits_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    """Even if there's no runtime dir at all, --run-id nonexistent → non-0."""
    from atdd.coach.commands.coach import run_status

    runtime_dir = tmp_path / ".atdd" / "runtime"
    # Do not create the runtime dir

    rc = run_status(["--run-id", "run-xyz"], runtime_dir=runtime_dir)

    assert rc != 0
