# URN: test:observe-and-correct:persona-shim-spawn-dispatch-wiring-gaps:E004-UNIT-003-fallback-to-direct-dispatch-when-no-cli-return
# Acceptance: acc:observe-and-correct:E004-UNIT-003-fallback-to-direct-dispatch-when-no-cli-return
# WMBT: wmbt:observe-and-correct:E004
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
"""E004-UNIT-003 — when ATDD_CORRECTION_TRANSPORT is unset or not 'cli-return',
cmd_spawn falls back to the existing direct-adapter dispatch path: no shim
wrapping, launch prompt via paste_text + send_key as before.

This is a regression guard: the shim opt-in path must not change behavior for
all existing callers that don't set ATDD_CORRECTION_TRANSPORT=cli-return.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.platform]


class _FakeMultiplexer:
    name = "fake"
    _counter = 0

    def __init__(self) -> None:
        self.surface_commands: list[str] = []
        self.paste_calls: list[str] = []

    def resolve_focused_pane(self, workspace: Any = None) -> str:
        return "pane:1"

    def new_surface_in_pane(
        self,
        pane_ref: Any = None,
        cwd: Any = None,
        command: Any = None,
        name: Any = None,
        workspace: Any = None,
    ) -> str:
        self.surface_commands.append(command or "")
        _FakeMultiplexer._counter += 1
        return f"surface:{_FakeMultiplexer._counter}"

    def new_surface(
        self,
        *,
        cwd: Any = None,
        command: Any = None,
        name: Any = None,
        workspace_ref: Any = None,
        pane_ref: Any = None,
        direction: Any = None,
    ) -> str:
        self.surface_commands.append(command or "")
        _FakeMultiplexer._counter += 1
        return f"surface:{_FakeMultiplexer._counter}"

    def rename(self, ref: str, name: str) -> None:
        pass

    def paste_text(self, ref: str, text: str) -> None:
        self.paste_calls.append(text)

    def send_key(self, *args: Any, **kwargs: Any) -> None:
        pass

    def capture_pane_text(self, *args: Any, **kwargs: Any) -> str:
        return ""


_SAMPLE_BODY = """\
## Issue Metadata

| Field | Value |
|-------|-------|
| Branch | `feat/wire-persona-shim-into-spawn-dispatch` |
| Train | `0002-coach-drives-lifecycle` |
"""

_PROMPT_TEXT = "launch prompt for issue 841"


def _run_cmd_spawn(tmp_path, multiplexer, monkeypatch):
    from atdd.coach.commands import spawn, session_template

    monkeypatch.setattr(
        session_template,
        "fetch_issue",
        lambda n: {"number": n, "title": "t", "body": _SAMPLE_BODY},
    )
    worktree = tmp_path / "wt"
    worktree.mkdir(exist_ok=True)
    runtime = tmp_path / "rt"
    prompt_file = worktree / "prompt.txt"
    prompt_file.write_text(_PROMPT_TEXT)

    with (
        patch("atdd.coach.commands.spawn._render_launch_prompt", return_value=prompt_file),
        patch("atdd.coach.commands.spawn.apply_canonical_name_and_layout"),
        patch("atdd.coach.commands.spawn._wait_for_claude_ready"),
        patch("atdd.coach.commands.spawn._pre_trust_worktree"),
        patch("atdd.coach.commands.spawn.compute_repo_short_name", return_value="test"),
        patch("atdd.coach.commands.spawn.compute_issue_surface_name", return_value="ATDD841"),
        patch("atdd.coach.commands.spawn._emit_agent_spawned_event"),
        patch("atdd.coach.commands.spawn._spawn_observer_if_configured"),
        patch("atdd.coach.utils.config.load_atdd_config", return_value=MagicMock()),
    ):
        spawn.cmd_spawn(
            persona="coder",
            llm="claude-code",
            worktree=worktree,
            issue=841,
            agent_id="coder-841-fallback",
            runtime_root=runtime,
            multiplexer=multiplexer,
        )
    return runtime


def test_no_shim_when_transport_is_not_set(tmp_path, monkeypatch):
    """When ATDD_CORRECTION_TRANSPORT is unset, the bare adapter command is used.

    This is a backward-compat guard: changing to cli-return must be opt-in only.
    """
    monkeypatch.delenv("ATDD_CORRECTION_TRANSPORT", raising=False)
    fake_mx = _FakeMultiplexer()
    _run_cmd_spawn(tmp_path, fake_mx, monkeypatch)

    assert fake_mx.surface_commands, "new_surface must be called"
    surface_cmd = fake_mx.surface_commands[-1]

    assert not surface_cmd.startswith("atdd-shim"), (
        f"Without ATDD_CORRECTION_TRANSPORT=cli-return, the command must NOT be "
        f"wrapped with atdd-shim. Got: {surface_cmd!r}"
    )
    assert "atdd.coach.shim" not in surface_cmd, (
        f"Without ATDD_CORRECTION_TRANSPORT=cli-return, the command must NOT "
        f"reference atdd.coach.shim. Got: {surface_cmd!r}"
    )


def test_no_shim_when_transport_is_multiplexer_send(tmp_path, monkeypatch):
    """When ATDD_CORRECTION_TRANSPORT=multiplexer-send, the existing direct path
    is used (no shim wrapping)."""
    monkeypatch.setenv("ATDD_CORRECTION_TRANSPORT", "multiplexer-send")
    fake_mx = _FakeMultiplexer()
    _run_cmd_spawn(tmp_path, fake_mx, monkeypatch)

    assert fake_mx.surface_commands, "new_surface must be called"
    surface_cmd = fake_mx.surface_commands[-1]

    assert not surface_cmd.startswith("atdd-shim"), (
        f"ATDD_CORRECTION_TRANSPORT=multiplexer-send must NOT trigger shim wrapping. "
        f"Got: {surface_cmd!r}"
    )


def test_no_cli_return_priming_when_transport_not_cli_return(tmp_path, monkeypatch):
    """When ATDD_CORRECTION_TRANSPORT is unset, no cli-return.jsonl inbox priming
    entry is written before the surface is created."""
    monkeypatch.delenv("ATDD_CORRECTION_TRANSPORT", raising=False)
    fake_mx = _FakeMultiplexer()
    runtime = _run_cmd_spawn(tmp_path, fake_mx, monkeypatch)

    cli_return_path = runtime / "agents" / "coder-841-fallback" / "cli-return.jsonl"
    if cli_return_path.exists():
        entries = [
            json.loads(ln)
            for ln in cli_return_path.read_text().splitlines()
            if ln.strip()
        ]
        assert entries == [], (
            f"cli-return.jsonl must NOT be primed when ATDD_CORRECTION_TRANSPORT "
            f"is not 'cli-return'. Found entries: {entries!r}"
        )
