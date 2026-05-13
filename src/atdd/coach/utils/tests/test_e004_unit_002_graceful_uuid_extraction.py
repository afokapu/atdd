# URN: test:integration-hardening:E004-UNIT-002-graceful-uuid-extraction
# Acceptance: acc:integration-hardening:E004-UNIT-002-graceful-uuid-extraction
# WMBT: wmbt:integration-hardening:E004
# Phase: RED
# Layer: application
"""E004-UNIT-002 — capture_session_uuid degrades gracefully when UUID is absent.

When the screen scrape does not find 'claude --resume <UUID>', the function:
  - must not raise
  - must return None
  - must not write a .session.json file
  - must print a warning to stderr

When the UUID IS present, it must persist the session JSON and return the UUID.
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

_SCREEN_WITH_UUID = (
    "Claude Max · Sonnet 4.6\n"
    f"Resume this session with: claude --resume {_VALID_UUID}\n"
    "> "
)
_SCREEN_WITHOUT_UUID = "Welcome to Claude Code.\n> "


class _FakeMx:
    name = "fake"

    def __init__(self, screen: str = "") -> None:
        self._screen = screen
        self.calls: list[dict] = []

    def read_screen(self, ref: str, lines: int = 50) -> str:
        self.calls.append({"op": "read_screen", "ref": ref, "lines": lines})
        return self._screen


def _call(tmp_path: Path, screen: str, **kwargs):
    mx = _FakeMx(screen=screen)
    return capture_session_uuid(
        mx, _SURFACE,
        issue=_ISSUE,
        agent_id=_AGENT_ID,
        canonical_name=_CANONICAL,
        persona="planner",
        phase="PLANNED",
        runtime_root=tmp_path,
        delay=0,
        **kwargs,
    )


def test_missing_uuid_returns_none(tmp_path, capsys):
    result = _call(tmp_path, _SCREEN_WITHOUT_UUID)
    assert result is None


def test_missing_uuid_does_not_write_file(tmp_path):
    _call(tmp_path, _SCREEN_WITHOUT_UUID)
    session_dir = tmp_path / "coach" / str(_ISSUE)
    assert not session_dir.exists() or not list(session_dir.glob("*.session.json"))


def test_missing_uuid_logs_warning(tmp_path, capsys):
    _call(tmp_path, _SCREEN_WITHOUT_UUID)
    err = capsys.readouterr().err
    assert "UUID not found" in err or "claude --resume" in err


def test_found_uuid_is_returned(tmp_path):
    result = _call(tmp_path, _SCREEN_WITH_UUID)
    assert result == _VALID_UUID


def test_found_uuid_writes_session_file(tmp_path):
    _call(tmp_path, _SCREEN_WITH_UUID)
    session_file = tmp_path / "coach" / str(_ISSUE) / f"{_AGENT_ID}.session.json"
    assert session_file.exists()
    data = json.loads(session_file.read_text())
    assert data["claude_resume_uuid"] == _VALID_UUID
    assert data["issue"] == _ISSUE
    assert data["agent_id"] == _AGENT_ID
    assert data["canonical_name"] == _CANONICAL
    assert data["cmux_surface"] == _SURFACE
    assert data["persona"] == "planner"
    assert data["phase"] == "PLANNED"


def test_found_uuid_session_file_has_iso_timestamp(tmp_path):
    _call(tmp_path, _SCREEN_WITH_UUID)
    session_file = tmp_path / "coach" / str(_ISSUE) / f"{_AGENT_ID}.session.json"
    data = json.loads(session_file.read_text())
    assert "spawned_at" in data
    assert "T" in data["spawned_at"]
