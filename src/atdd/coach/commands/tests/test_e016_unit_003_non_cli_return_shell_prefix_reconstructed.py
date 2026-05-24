"""E016-UNIT-003 — non-cli-return path reconstructs shell prefix from env_overrides.

RED: fails until cmd_spawn handles the tuple return of _inject_agent_env
and reconstructs the shell prefix for the multiplexer dispatch path.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from atdd.coach.commands.spawn import cmd_spawn


class FakeMultiplexer:
    def __init__(self):
        self.surface_commands = []
        self.paste_calls = []
        self.send_key_calls = []
        self.surfaces = {}

    def new_surface(self, name, command, **kwargs):
        self.surface_commands.append(command)
        self.surfaces[name] = command
        return MagicMock()

    def resolve_focused_pane(self, **kwargs):
        return MagicMock()

    def capture_pane_text(self, *args, **kwargs):
        return ""

    def paste_text(self, *args, **kwargs):
        self.paste_calls.append(args)

    def send_key(self, *args, **kwargs):
        self.send_key_calls.append(args)

    def rename_surface(self, *args, **kwargs):
        pass

    def apply_layout(self, *args, **kwargs):
        pass

    def new_surface_in_pane(self, *args, **kwargs):
        cmd = kwargs.get("command", "")
        self.surface_commands.append(cmd)
        return MagicMock()


@pytest.fixture()
def non_cli_return_env(monkeypatch):
    monkeypatch.delenv("ATDD_CORRECTION_TRANSPORT", raising=False)


def test_shell_prefix_present_in_non_cli_return_command(tmp_path, non_cli_return_env):
    mux = FakeMultiplexer()
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    runtime_root = tmp_path / "runtime"

    with (
        patch("atdd.coach.commands.spawn._pre_trust_worktree"),
        patch("atdd.coach.commands.spawn._assert_worker_processing"),
        patch("atdd.coach.commands.spawn._apply_canonical_name_and_layout"),
        patch("atdd.coach.commands.spawn._write_manifest"),
        patch("atdd.coach.commands.spawn._emit_agent_spawned"),
        patch("atdd.coach.commands.spawn.compute_repo_short_name", return_value="atdd"),
        patch("atdd.coach.commands.spawn.compute_issue_surface_name", return_value="ATDD854"),
        patch("atdd.coach.commands.spawn._build_launch_prompt", return_value=(tmp_path / "lp.txt")),
        patch("atdd.coach.commands.spawn._agent_runtime_dir", return_value=tmp_path / "agent"),
        patch("atdd.coach.commands.spawn.load_atdd_config", return_value=MagicMock()),
    ):
        (tmp_path / "lp.txt").write_text("launch prompt")
        (tmp_path / "agent").mkdir(parents=True, exist_ok=True)
        cmd_spawn(
            persona="planner",
            issue=854,
            worktree=worktree,
            phase="planned",
            rules=[],
            llm="claude-code",
            multiplexer=mux,
            agent_id="planner-854-test",
            runtime_root=runtime_root,
        )

    assert mux.surface_commands, "FakeMultiplexer received no surface command"
    surface_cmd = mux.surface_commands[-1]
    assert surface_cmd.startswith("ATDD_AGENT_ID=planner-854-test"), (
        f"Expected shell prefix in non-cli-return command, got: {surface_cmd!r}"
    )
    assert "--env" not in surface_cmd, (
        f"'--env' flag must not appear in non-cli-return shell command: {surface_cmd!r}"
    )
