# URN: test:integration-hardening:E004-UNIT-002-graceful-uuid-extraction
# Acceptance: acc:integration-hardening:E004-UNIT-002-graceful-uuid-extraction
# WMBT: wmbt:integration-hardening:E004
# Phase: RED
# Layer: application
"""E004-UNIT-002 — capture_session_uuid degrades gracefully when no session file exists.

Post-#691 behavior: capture_session_uuid no longer screen-scrapes for
'claude --resume <UUID>' (Claude Code does not print that on startup). Instead
it reads the most-recent jsonl filename under ~/.claude/projects/<key>/.

When no session jsonl file exists for the project yet:
  - must not raise
  - must return None
  - must not write a .session.json file
  - must print a warning to stderr

When a session jsonl IS present, it must persist the session JSON and return
the UUID parsed from the filename.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from atdd.coach.utils.session_naming_apply import capture_session_uuid

pytestmark = [pytest.mark.coach]

_ISSUE = 582
_AGENT_ID = "planner-582-001"
_CANONICAL = "ATDD582-issue-582"
_SURFACE = "surface:1"
_VALID_UUID = "0ccd5309-7dbf-4590-bf92-7d128903bd42"


class _FakeMx:
    name = "fake"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def read_screen(self, ref: str, lines: int = 50) -> str:
        # Post-#691 fix: capture_session_uuid no longer calls read_screen.
        # If it does, that's a regression — record the call for assertion.
        self.calls.append({"op": "read_screen", "ref": ref, "lines": lines})
        return ""


def _seed_claude_session(home: Path, worktree_cwd: Path, uuid: str) -> Path:
    """Create a fake ~/.claude/projects/<key>/<uuid>.jsonl file."""
    project_key = str(worktree_cwd.resolve()).replace("/", "-").replace(".", "-")
    project_dir = home / ".claude" / "projects" / project_key
    project_dir.mkdir(parents=True, exist_ok=True)
    jsonl = project_dir / f"{uuid}.jsonl"
    jsonl.write_text('{"role":"system","content":"seeded"}\n')
    return jsonl


def _call(
    tmp_path: Path,
    *,
    seed_uuid: str | None = None,
    monkeypatch: pytest.MonkeyPatch | None = None,
):
    """Run capture_session_uuid against a fixture ~/.claude/projects layout."""
    home = tmp_path / "home"
    home.mkdir()
    if monkeypatch is not None:
        monkeypatch.setenv("HOME", str(home))
    worktree_cwd = tmp_path / "worktree"
    worktree_cwd.mkdir()
    if seed_uuid is not None:
        _seed_claude_session(home, worktree_cwd, seed_uuid)
    runtime_root = tmp_path / "runtime"
    mx = _FakeMx()
    return capture_session_uuid(
        mx, _SURFACE,
        issue=_ISSUE,
        agent_id=_AGENT_ID,
        canonical_name=_CANONICAL,
        persona="planner",
        phase="PLANNED",
        runtime_root=runtime_root,
        delay=0,
        worktree_cwd=worktree_cwd,
    )


def test_missing_uuid_returns_none(tmp_path, monkeypatch, capsys):
    result = _call(tmp_path, seed_uuid=None, monkeypatch=monkeypatch)
    assert result is None


def test_missing_uuid_does_not_write_file(tmp_path, monkeypatch):
    _call(tmp_path, seed_uuid=None, monkeypatch=monkeypatch)
    session_dir = tmp_path / "runtime" / "coach" / str(_ISSUE)
    assert not session_dir.exists() or not list(session_dir.glob("*.session.json"))


def test_missing_uuid_logs_warning(tmp_path, monkeypatch, capsys):
    _call(tmp_path, seed_uuid=None, monkeypatch=monkeypatch)
    err = capsys.readouterr().err
    assert "no claude session jsonl found" in err


def test_found_uuid_is_returned(tmp_path, monkeypatch):
    result = _call(tmp_path, seed_uuid=_VALID_UUID, monkeypatch=monkeypatch)
    assert result == _VALID_UUID


def test_found_uuid_writes_session_file(tmp_path, monkeypatch):
    _call(tmp_path, seed_uuid=_VALID_UUID, monkeypatch=monkeypatch)
    session_file = tmp_path / "runtime" / "coach" / str(_ISSUE) / f"{_AGENT_ID}.session.json"
    assert session_file.exists()
    data = json.loads(session_file.read_text())
    assert data["claude_resume_uuid"] == _VALID_UUID
    assert data["issue"] == _ISSUE
    assert data["agent_id"] == _AGENT_ID
    assert data["canonical_name"] == _CANONICAL
    assert data["cmux_surface"] == _SURFACE
    assert data["persona"] == "planner"
    assert data["phase"] == "PLANNED"


def test_found_uuid_session_file_has_iso_timestamp(tmp_path, monkeypatch):
    _call(tmp_path, seed_uuid=_VALID_UUID, monkeypatch=monkeypatch)
    session_file = tmp_path / "runtime" / "coach" / str(_ISSUE) / f"{_AGENT_ID}.session.json"
    data = json.loads(session_file.read_text())
    assert "spawned_at" in data
    assert "T" in data["spawned_at"]


def test_no_screen_scrape_called(tmp_path, monkeypatch):
    """Post-#691 regression guard: read_screen must NOT be invoked."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    worktree_cwd = tmp_path / "worktree"
    worktree_cwd.mkdir()
    _seed_claude_session(home, worktree_cwd, _VALID_UUID)
    mx = _FakeMx()
    capture_session_uuid(
        mx, _SURFACE,
        issue=_ISSUE,
        agent_id=_AGENT_ID,
        canonical_name=_CANONICAL,
        persona="planner",
        phase="PLANNED",
        runtime_root=tmp_path / "runtime",
        delay=0,
        worktree_cwd=worktree_cwd,
    )
    assert not any(c["op"] == "read_screen" for c in mx.calls), (
        f"read_screen should not be called post-#691 fix; calls={mx.calls}"
    )
