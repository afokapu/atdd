"""
Unit tests for the multiplexer abstraction.

SPEC-COACH-ORCH-0003: auto-detect cmux (preferred) or tmux (fallback).

Run: PYTHONPATH=src python3 -m pytest -q src/atdd/coach/commands/tests/test_multiplexer.py -v
"""
from __future__ import annotations

import subprocess
from unittest.mock import patch, MagicMock

import pytest

from atdd.coach.utils.multiplexer import (
    CmuxBackend,
    MultiplexerError,
    TmuxBackend,
    detect_multiplexer,
    get_multiplexer,
)

pytestmark = [pytest.mark.platform]


# ---------------------------------------------------------------------------
# detect_multiplexer / get_multiplexer
# ---------------------------------------------------------------------------


def _fake_run_success(*args, **kwargs):
    return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="v1", stderr="")


def test_detect_prefers_cmux_when_available():
    with patch("atdd.coach.utils.multiplexer.shutil.which", side_effect=lambda b: f"/bin/{b}"), \
         patch("atdd.coach.utils.multiplexer.subprocess.run", side_effect=_fake_run_success):
        assert detect_multiplexer() == "cmux"


def test_detect_falls_back_to_tmux_when_cmux_missing():
    def which(binary):
        return "/bin/tmux" if binary == "tmux" else None

    with patch("atdd.coach.utils.multiplexer.shutil.which", side_effect=which), \
         patch("atdd.coach.utils.multiplexer.subprocess.run", side_effect=_fake_run_success):
        assert detect_multiplexer() == "tmux"


def test_detect_returns_none_when_neither_available():
    with patch("atdd.coach.utils.multiplexer.shutil.which", return_value=None):
        assert detect_multiplexer() is None


def test_get_multiplexer_with_cmux_preferred():
    backend = get_multiplexer(preferred="cmux")
    assert isinstance(backend, CmuxBackend)
    assert backend.name == "cmux"


def test_get_multiplexer_with_tmux_preferred():
    backend = get_multiplexer(preferred="tmux")
    assert isinstance(backend, TmuxBackend)
    assert backend.name == "tmux"


def test_get_multiplexer_raises_when_none_detected():
    with patch("atdd.coach.utils.multiplexer.detect_multiplexer", return_value=None):
        with pytest.raises(MultiplexerError, match="No multiplexer available"):
            get_multiplexer()


# ---------------------------------------------------------------------------
# CmuxBackend operations (mocked subprocess)
# ---------------------------------------------------------------------------


def _make_result(stdout: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


def test_cmux_new_workspace_invokes_correct_command():
    backend = CmuxBackend()
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _make_result(stdout="workspace:5\n")

    with patch("atdd.coach.utils.multiplexer.subprocess.run", side_effect=fake_run):
        ref = backend.new_workspace("/tmp/wt", "claude", name="issue-257")

    assert ref == "workspace:5"
    assert captured["cmd"][:2] == ["cmux", "new-workspace"]
    assert "--cwd" in captured["cmd"]
    assert "/tmp/wt" in captured["cmd"]
    assert "--command" in captured["cmd"]
    assert "claude" in captured["cmd"]
    assert "issue-257" in captured["cmd"]


def test_cmux_read_screen_returns_stdout():
    backend = CmuxBackend()
    with patch(
        "atdd.coach.utils.multiplexer.subprocess.run",
        return_value=_make_result(stdout="line1\nline2\n"),
    ):
        out = backend.read_screen("workspace:1", lines=10)
    assert out == "line1\nline2\n"


def test_cmux_list_workspaces_parses_lines():
    backend = CmuxBackend()
    with patch(
        "atdd.coach.utils.multiplexer.subprocess.run",
        return_value=_make_result(stdout="workspace:1\nworkspace:2\n\n"),
    ):
        assert backend.list_workspaces() == ["workspace:1", "workspace:2"]


def test_cmux_send_and_close_invoke_cmux_cli():
    backend = CmuxBackend()
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _make_result()

    with patch("atdd.coach.utils.multiplexer.subprocess.run", side_effect=fake_run):
        backend.send("workspace:1", "hello")
        backend.send_key("workspace:1", "Enter")
        backend.close("workspace:1")

    assert calls[0][:3] == ["cmux", "send", "--workspace"]
    assert calls[1][:3] == ["cmux", "send-key", "--workspace"]
    assert calls[2][:3] == ["cmux", "close-workspace", "--workspace"]


def test_cmux_missing_binary_raises_multiplexer_error():
    backend = CmuxBackend()
    with patch("atdd.coach.utils.multiplexer.subprocess.run", side_effect=FileNotFoundError):
        with pytest.raises(MultiplexerError, match="binary not found"):
            backend.read_screen("workspace:1")


# ---------------------------------------------------------------------------
# TmuxBackend operations
# ---------------------------------------------------------------------------


def test_tmux_new_workspace_uses_new_session():
    backend = TmuxBackend()
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _make_result()

    with patch("atdd.coach.utils.multiplexer.subprocess.run", side_effect=fake_run):
        ref = backend.new_workspace("/tmp/wt", "claude", name="sess1")

    assert ref == "sess1"
    assert captured["cmd"][:3] == ["tmux", "new-session", "-d"]
    assert "sess1" in captured["cmd"]
    assert "/tmp/wt" in captured["cmd"]


def test_tmux_read_screen_uses_capture_pane():
    backend = TmuxBackend()
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _make_result(stdout="screen contents")

    with patch("atdd.coach.utils.multiplexer.subprocess.run", side_effect=fake_run):
        out = backend.read_screen("sess1", lines=25)

    assert out == "screen contents"
    assert captured["cmd"][:2] == ["tmux", "capture-pane"]
    assert "-p" in captured["cmd"]
    assert "-25" in captured["cmd"]


def test_tmux_list_workspaces_parses_sessions():
    backend = TmuxBackend()
    with patch(
        "atdd.coach.utils.multiplexer.subprocess.run",
        return_value=_make_result(stdout="sess1\nsess2\n"),
    ):
        assert backend.list_workspaces() == ["sess1", "sess2"]


def test_tmux_close_uses_kill_session():
    backend = TmuxBackend()
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _make_result()

    with patch("atdd.coach.utils.multiplexer.subprocess.run", side_effect=fake_run):
        backend.close("sess1")

    assert captured["cmd"][:2] == ["tmux", "kill-session"]
    assert "sess1" in captured["cmd"]
