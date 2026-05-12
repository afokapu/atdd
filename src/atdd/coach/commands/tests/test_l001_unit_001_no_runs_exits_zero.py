# URN: test:drive-state-machine:coach-state-machine-and-runtime:L001-UNIT-001-no-runs-exits-zero
# Acceptance: acc:drive-state-machine:L001-UNIT-001-no-runs-exits-zero
# WMBT: wmbt:drive-state-machine:L001
# Phase: RED
# Layer: application
# Assertion: behavioral
"""`atdd coach status` with no runtime directory or empty coach/ dir exits 0
with a clear 'no runs found' message.

Issue #616. Spec: issue body GT-001.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def test_status_no_runtime_dir_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    """When .atdd/runtime/coach/ does not exist at all, exit 0 and print message."""
    from atdd.coach.commands.coach import run_status

    runtime_dir = tmp_path / ".atdd" / "runtime"
    # Do NOT create the runtime dir — it should not exist

    rc = run_status([], runtime_dir=runtime_dir)
    out = capsys.readouterr().out

    assert rc == 0
    assert "No coach runs found" in out


def test_status_empty_coach_dir_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    """When .atdd/runtime/coach/ exists but has no decisions.jsonl, exit 0."""
    from atdd.coach.commands.coach import run_status

    runtime_dir = tmp_path / ".atdd" / "runtime"
    (runtime_dir / "coach").mkdir(parents=True)

    rc = run_status([], runtime_dir=runtime_dir)
    out = capsys.readouterr().out

    assert rc == 0
    assert "No coach runs found" in out


def test_status_no_runs_message_mentions_runtime_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    """The 'no runs' message should include the path to .atdd/runtime/coach/."""
    from atdd.coach.commands.coach import run_status

    runtime_dir = tmp_path / ".atdd" / "runtime"

    run_status([], runtime_dir=runtime_dir)
    out = capsys.readouterr().out

    assert ".atdd/runtime/coach" in out or "runtime/coach" in out
