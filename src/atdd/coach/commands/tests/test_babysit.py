"""
Unit tests for `atdd babysit`.

SPEC-COACH-ORCH-0004: auto-approve known-safe, escalate unknowns.
SPEC-COACH-ORCH-0005: detect policy violations.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from atdd.coach.commands.babysit import (
    BabysitDecision,
    DEFAULT_LOG_PATH,
    WorkspaceState,
    classify_prompt,
    detect_violation,
    log_event,
    process_workspace,
)

pytestmark = [pytest.mark.platform]


# ---------------------------------------------------------------------------
# classify_prompt
# ---------------------------------------------------------------------------


_PROMPT_MARKER = "Do you want to proceed?\n❯ 1. Yes\n  2. No\n"


def test_classify_idle_when_no_prompt_marker():
    assert classify_prompt("just some logs").action == "idle"


def test_classify_auto_approves_read_tool():
    screen = "Read(/tmp/foo.txt)\n" + _PROMPT_MARKER
    decision = classify_prompt(screen)
    assert decision.action == "auto_approve"
    assert decision.matched == "Read"


def test_classify_auto_approves_edit_tool():
    screen = "Edit(src/foo.py)\n" + _PROMPT_MARKER
    decision = classify_prompt(screen)
    assert decision.action == "auto_approve"
    assert decision.matched == "Edit"


def test_classify_auto_approves_git_status():
    screen = "Bash(git status)\n" + _PROMPT_MARKER
    # Bash is always-escalate even though git status is known-safe
    decision = classify_prompt(screen)
    assert decision.action == "escalate"
    assert decision.matched == "Bash"


def test_classify_escalates_write():
    screen = "Write(/etc/passwd)\n" + _PROMPT_MARKER
    decision = classify_prompt(screen)
    assert decision.action == "escalate"
    assert decision.matched == "Write"


def test_classify_escalates_bash():
    screen = "Bash(rm -rf /)\n" + _PROMPT_MARKER
    decision = classify_prompt(screen)
    assert decision.action == "escalate"


def test_classify_escalates_unknown():
    screen = "SomeNovelTool(args)\n" + _PROMPT_MARKER
    decision = classify_prompt(screen)
    assert decision.action == "escalate"


# ---------------------------------------------------------------------------
# detect_violation
# ---------------------------------------------------------------------------


def test_detect_violation_atdd_hand_edit():
    screen = "Edit(.atdd/manifest.yaml)"
    v = detect_violation(screen)
    assert v is not None
    assert v.action == "violation"
    assert ".atdd/" in v.matched


def test_detect_violation_smoke_skip():
    screen = "Running: atdd issue 42 --status REFACTOR now"
    v = detect_violation(screen)
    assert v is not None
    assert "SMOKE" in v.matched


def test_detect_violation_none_on_benign():
    assert detect_violation("everything is fine") is None


# ---------------------------------------------------------------------------
# log_event
# ---------------------------------------------------------------------------


def test_log_event_appends_jsonl(tmp_path: Path):
    log = tmp_path / "orch.jsonl"
    log_event({"event": "test", "a": 1}, path=log)
    log_event({"event": "test", "a": 2}, path=log)
    lines = log.read_text().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["event"] == "test"
    assert first["a"] == 1
    assert "ts" in first


# ---------------------------------------------------------------------------
# process_workspace
# ---------------------------------------------------------------------------


def _backend_with_screen(screen: str) -> MagicMock:
    backend = MagicMock()
    backend.read_screen.return_value = screen
    return backend


def test_process_workspace_auto_approves_sends_enter(tmp_path: Path):
    log = tmp_path / "log.jsonl"
    backend = _backend_with_screen("Read(/tmp/a)\n" + _PROMPT_MARKER)
    state = WorkspaceState(ref="ws:1")

    decision = process_workspace(backend, state, 15, 30, log_path=log)

    assert decision.action == "auto_approve"
    backend.send.assert_called_once_with("ws:1", "1")
    backend.send_key.assert_called_once_with("ws:1", "Enter")
    events = [json.loads(line) for line in log.read_text().splitlines()]
    assert any(e["event"] == "auto_approve" for e in events)


def test_process_workspace_logs_violation(tmp_path: Path):
    log = tmp_path / "log.jsonl"
    backend = _backend_with_screen("Edit(.atdd/manifest.yaml)\n" + _PROMPT_MARKER)
    state = WorkspaceState(ref="ws:1")

    decision = process_workspace(backend, state, 15, 30, log_path=log)

    assert decision.action == "violation"
    backend.send.assert_not_called()
    events = [json.loads(line) for line in log.read_text().splitlines()]
    assert any(e["event"] == "violation" for e in events)


def test_process_workspace_stale_escalates(tmp_path: Path):
    log = tmp_path / "log.jsonl"
    backend = _backend_with_screen("boring idle screen")
    state = WorkspaceState(ref="ws:1")
    state.last_screen_hash = ""  # will become set on first read
    # first read — establish baseline
    process_workspace(backend, state, 15, 30, log_path=log)
    # force staleness
    state.last_change_ts = time.time() - (40 * 60)
    decision = process_workspace(backend, state, 15, 30, log_path=log)
    assert decision.action == "escalate"
    assert "stale" in decision.matched
