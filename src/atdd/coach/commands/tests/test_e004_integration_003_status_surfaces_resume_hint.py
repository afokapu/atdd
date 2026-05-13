# URN: test:integration-hardening:coach-spawn-wiring:E004-INTEGRATION-003-status-surfaces-resume-hint
# Acceptance: acc:integration-hardening:E004-INTEGRATION-003-status-surfaces-resume-hint
# WMBT: wmbt:integration-hardening:E004
# Phase: RED
# Layer: integration
"""E004-INTEGRATION-003 — atdd coach status renders 'Resume agent: claude --resume <UUID>'.

Writes a .session.json file to a tmp runtime dir, calls run_status, and asserts
the human-readable output contains the resume hint line.
"""
from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pytest

from atdd.coach.commands.coach_status import run_status

pytestmark = [pytest.mark.platform]

VALID_UUID = "0ccd5309-7dbf-4590-bf92-7d128903bd42"
AGENT_ID = "planner-652-001"
ISSUE = 652


def _write_session(runtime_dir: Path) -> None:
    session_dir = runtime_dir / "coach" / str(ISSUE)
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / f"{AGENT_ID}.session.json").write_text(
        json.dumps({
            "issue": ISSUE,
            "agent_id": AGENT_ID,
            "canonical_name": "ATDD652-fix-652-claude-session-rename",
            "cmux_surface": "surface:1",
            "claude_resume_uuid": VALID_UUID,
            "spawned_at": "2026-05-13T19:00:00Z",
            "persona": "planner",
            "phase": "PLANNED",
        }, indent=2)
    )


def test_status_includes_resume_hint(tmp_path: Path, capsys) -> None:
    """run_status output contains 'Resume agent: claude --resume <UUID>'."""
    _write_session(tmp_path)

    rc = run_status([], runtime_dir=tmp_path)

    captured = capsys.readouterr()
    assert f"claude --resume {VALID_UUID}" in captured.out, (
        f"Expected 'claude --resume {VALID_UUID}' in status output; got:\n{captured.out}"
    )
    assert AGENT_ID in captured.out, (
        f"Expected agent_id '{AGENT_ID}' in status output; got:\n{captured.out}"
    )


def test_status_json_includes_sessions(tmp_path: Path, capsys) -> None:
    """run_status --json includes sessions array with the UUID entry."""
    _write_session(tmp_path)

    rc = run_status(["--json"], runtime_dir=tmp_path)

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "sessions" in data
    assert any(s.get("claude_resume_uuid") == VALID_UUID for s in data["sessions"]), (
        f"Expected session with UUID {VALID_UUID!r} in sessions; got: {data['sessions']}"
    )
