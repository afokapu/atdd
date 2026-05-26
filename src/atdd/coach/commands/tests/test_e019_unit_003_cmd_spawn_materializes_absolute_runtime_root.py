# URN: test:spawn-agents:E019-UNIT-003-cmd-spawn-materializes-absolute-runtime-root
# Acceptance: acc:spawn-agents:E019-UNIT-003-cmd-spawn-materializes-absolute-runtime-root
# WMBT: wmbt:spawn-agents:E019
# Phase: GREEN
# Assertion: behavioral
"""E019-UNIT-003 — cmd_spawn resolves runtime_root to absolute at construction time
so every downstream callee (including _build_shim_command) receives an absolute Path.

Monkeypatches _build_shim_command to capture its runtime_root argument without
executing the shim; verifies the received Path.is_absolute() is True.

RED: fails until cmd_spawn calls Path(runtime_root).resolve() before passing
runtime_root to _build_shim_command.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch


class _FakeMux:
    name = "fake"

    def resolve_focused_pane(self, workspace=None) -> str:
        return "pane:860"

    def new_surface(self, *a, **kw):
        return "surface:860"

    def new_surface_in_pane(self, pane_ref=None, cwd=None, command=None, name=None, **kw) -> str:
        return "surface:860"

    def new_workspace(self, *a, **kw):
        return "ws-860"

    def paste_text(self, *a, **kw):
        pass

    def send_key(self, *a, **kw):
        pass

    def send(self, *a, **kw):
        pass

    def rename(self, *a, **kw):
        pass

    def list_surfaces(self, **kw):
        return []

    def capture_pane_text(self, *a, **kw):
        return ""


class _CaptureBuildShimCommand(Exception):
    """Raised by the spy to abort cmd_spawn early while carrying runtime_root."""
    def __init__(self, runtime_root: Path):
        self.runtime_root = runtime_root


def test_cmd_spawn_passes_absolute_runtime_root_to_build_shim_command(tmp_path, monkeypatch):
    from atdd.coach.commands.spawn import cmd_spawn

    monkeypatch.setenv("ATDD_CORRECTION_TRANSPORT", "cli-return")

    worktree = tmp_path / "issue-860-wt"
    worktree.mkdir()

    # Relative runtime_root — the key input for this test
    relative_runtime_root = ".atdd/runtime"

    captured: list[Path] = []

    def _spy_build_shim_command(adapter_command, agent_id, runtime_root, **kw):
        captured.append(runtime_root)
        raise _CaptureBuildShimCommand(runtime_root)

    with (
        patch("atdd.coach.commands.spawn._build_shim_command", side_effect=_spy_build_shim_command),
        patch("atdd.coach.commands.spawn._render_launch_prompt", return_value=worktree / ".lp.txt"),
        patch("atdd.coach.commands.spawn.apply_canonical_name_and_layout"),
        patch("atdd.coach.commands.spawn._pre_trust_worktree"),
        patch("atdd.coach.commands.spawn.compute_repo_short_name", return_value="test"),
        patch("atdd.coach.commands.spawn.compute_issue_surface_name", return_value="ATDD860"),
        patch("atdd.coach.utils.config.load_atdd_config", return_value=MagicMock()),
        patch("atdd.coach.commands.spawn._prime_cli_return_inbox"),
        patch("atdd.coach.commands.spawn._inject_agent_env", return_value=({}, "echo ok")),
        patch("atdd.coach.commands.spawn._assert_no_forbidden_flags"),
    ):
        # Create a minimal launch-prompt file so _render_launch_prompt stub works
        lp = worktree / ".lp.txt"
        lp.write_text("launch prompt")

        try:
            cmd_spawn(
                persona="planner",
                llm="claude-code",
                worktree=worktree,
                issue=860,
                agent_id="planner-860-unit003",
                runtime_root=relative_runtime_root,
                multiplexer=_FakeMux(),
            )
        except _CaptureBuildShimCommand:
            pass

    assert captured, (
        "E019-UNIT-003: _build_shim_command was never called — "
        "check that ATDD_CORRECTION_TRANSPORT=cli-return is set and cmd_spawn reaches the shim path."
    )
    received = captured[0]
    assert isinstance(received, Path), (
        f"E019-UNIT-003: _build_shim_command must receive a Path, got {type(received)!r}"
    )
    assert received.is_absolute(), (
        f"E019-UNIT-003: cmd_spawn must resolve runtime_root to absolute before passing it "
        f"to _build_shim_command. Got: {received!r} (relative). "
        "Fix: add runtime_root = Path(runtime_root).resolve() in cmd_spawn."
    )
