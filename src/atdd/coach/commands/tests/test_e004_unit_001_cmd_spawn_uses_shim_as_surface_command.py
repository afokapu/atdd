# URN: test:observe-and-correct:persona-shim-spawn-dispatch-wiring-gaps:E004-UNIT-001-cmd-spawn-uses-shim-as-surface-command
# Acceptance: acc:observe-and-correct:E004-UNIT-001-cmd-spawn-uses-shim-as-surface-command
# WMBT: wmbt:observe-and-correct:E004
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
"""E004-UNIT-001 — cmd_spawn passes a PersonaShim wrapper command (not the bare
adapter) as the surface command when ATDD_CORRECTION_TRANSPORT=cli-return.

RED: cmd_spawn currently passes the bare adapter command (e.g.
``ATDD_AGENT_ID=... claude --permission-mode acceptEdits ...``) directly to
new_surface. PersonaShim is never instantiated in the dispatch path. This test
pins the desired behavior: the pane command must start with ``atdd-shim`` (the
shim entry point) and the adapter command must appear as an argument to the shim.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.platform]


class _FakeMultiplexer:
    """Records new_surface_in_pane calls to capture the command string."""

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


def test_cmd_spawn_uses_shim_command_when_cli_return_transport(tmp_path, monkeypatch):
    """When ATDD_CORRECTION_TRANSPORT=cli-return, the command passed to the
    multiplexer surface starts with ``atdd-shim``, not the bare adapter.

    RED: this assertion fails because cmd_spawn passes the bare adapter command.
    """
    from atdd.coach.commands import spawn, session_template

    monkeypatch.setenv("ATDD_CORRECTION_TRANSPORT", "cli-return")
    monkeypatch.setattr(
        session_template,
        "fetch_issue",
        lambda n: {"number": n, "title": "t", "body": _SAMPLE_BODY},
    )

    worktree = tmp_path / "wt"
    worktree.mkdir()
    runtime = tmp_path / "rt"
    prompt_file = worktree / "prompt.txt"
    prompt_file.write_text("launch prompt content")

    fake_mx = _FakeMultiplexer()

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
            agent_id="coder-841-abc",
            runtime_root=runtime,
            multiplexer=fake_mx,
        )

    assert fake_mx.surface_commands, "cmd_spawn must have called new_surface at least once"
    surface_cmd = fake_mx.surface_commands[-1]

    # RED assertion: the command must start with the shim entry point.
    assert surface_cmd.startswith("atdd-shim") or "atdd.coach.shim" in surface_cmd, (
        f"When ATDD_CORRECTION_TRANSPORT=cli-return, the surface command must start with "
        f"'atdd-shim' (or invoke atdd.coach.shim as a module). "
        f"Got: {surface_cmd!r}"
    )

    # The bare adapter token (e.g. 'claude') must appear AFTER the shim prefix,
    # not as the first word.
    words = surface_cmd.split()
    assert words[0] not in ("claude", "ATDD_AGENT_ID="), (
        f"The bare adapter must NOT be the first token in the surface command when "
        f"ATDD_CORRECTION_TRANSPORT=cli-return. Got: {surface_cmd!r}"
    )


def test_cmd_spawn_shim_command_includes_agent_id_and_runtime(tmp_path, monkeypatch):
    """The shim command must carry --agent-id and --runtime-dir so PersonaShim
    can locate cli-return.jsonl.

    RED: fails because no shim wrapping exists.
    """
    from atdd.coach.commands import spawn, session_template

    monkeypatch.setenv("ATDD_CORRECTION_TRANSPORT", "cli-return")
    monkeypatch.setattr(
        session_template,
        "fetch_issue",
        lambda n: {"number": n, "title": "t", "body": _SAMPLE_BODY},
    )

    worktree = tmp_path / "wt"
    worktree.mkdir()
    runtime = tmp_path / "rt"
    prompt_file = worktree / "prompt.txt"
    prompt_file.write_text("launch prompt")

    fake_mx = _FakeMultiplexer()

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
            agent_id="coder-841-xyz",
            runtime_root=runtime,
            multiplexer=fake_mx,
        )

    assert fake_mx.surface_commands, "new_surface must be called"
    surface_cmd = fake_mx.surface_commands[-1]

    # RED: --agent-id and --runtime-dir must appear in the shim command.
    assert "coder-841-xyz" in surface_cmd, (
        f"agent_id 'coder-841-xyz' must appear in shim command so PersonaShim "
        f"can locate the runtime dir. Got: {surface_cmd!r}"
    )
    assert str(runtime) in surface_cmd or "--runtime-dir" in surface_cmd, (
        f"--runtime-dir must appear in shim command so PersonaShim can find "
        f"cli-return.jsonl. Got: {surface_cmd!r}"
    )
