# URN: test:govern-lifecycle:coach-single-instance-lock-and-zombie-reaping:E011-UNIT-005-run-refuses-second-coach-with-clear-message
# Acceptance: acc:govern-lifecycle:E011-UNIT-005-run-refuses-second-coach-with-clear-message
# WMBT: wmbt:govern-lifecycle:E011
# Phase: GREEN
# Layer: backend.unit
# Assertion: behavioral

"""acc:govern-lifecycle:E011-UNIT-005 — _drive_single_issue returns 1 when live lock held."""
from __future__ import annotations

import json
import os
import sys

import pytest

from atdd.coach.commands.coach import Config, _drive_single_issue, initialize_state_machine, Phase


def test_run_refuses_second_coach_with_clear_message(tmp_path, capsys):
    # Plant a live lockfile (current PID is always alive).
    lock_dir = tmp_path / "coach" / "99"
    lock_dir.mkdir(parents=True)
    (lock_dir / "coach.lock").write_text(
        json.dumps({"pid": os.getpid(), "issue": 99, "started_at": "2026-05-19T00:00:00Z"}),
        encoding="utf-8",
    )

    cfg = Config(issue_numbers=[99], dry_run=False)
    sm = initialize_state_machine(99)

    rc = _drive_single_issue(cfg, sm, tmp_path, _max_loop_events=0)

    assert rc == 1, "must refuse with non-zero exit code"
    captured = capsys.readouterr()
    combined = (captured.out + captured.err).lower()
    assert "already running" in combined or "pid" in combined, (
        "error message must mention 'already running' or 'pid'"
    )
