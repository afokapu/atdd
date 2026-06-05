# URN: test:govern-lifecycle:cmux-native-worker-launcher:E043-UNIT-001-cmux-native-launch-seeds-prompt-first
# Acceptance: acc:govern-lifecycle:E043-UNIT-001-cmux-native-launch-seeds-prompt-first
# WMBT: wmbt:govern-lifecycle:E043
# Phase: GREEN
"""acc:govern-lifecycle:E043-UNIT-001 — the cmux-native launcher seeds the worker's
first turn via the agent's POSITIONAL prompt (prompt-before-flags), wraps it in a
``cmux new-workspace --command`` launch, and never emits a forbidden bypass flag.

#978 RED→GREEN: replace the pty shim launch transport with a cmux-native launch.
The shim's whole reason to exist (reliably inject + submit a prompt into a live TUI)
disappears — the agent's positional prompt seeds AND auto-submits the first turn
(verified 2026-06-05 spike). Decision communication rides the cmux Feed (the cmux
wrapper's hooks), not this layer.
"""
from __future__ import annotations

import shlex
from pathlib import Path

import pytest

from atdd.runtime.agent_control import (
    AgentSignal,
    CmuxAgentController,
    DispatchSpec,
)
from atdd.runtime.agent_control.cmux_launch import (
    build_agent_seed_argv,
    build_cmux_launch_argv,
)

pytestmark = [pytest.mark.coder]


def _spec(tmp_path: Path, *, prompt: str = "Work issue #978", mode: str = "acceptEdits",
          tools=("Read", "Edit")) -> DispatchSpec:
    return DispatchSpec(
        agent_id="coder-978-001",
        persona="coder",
        worktree_path=tmp_path,
        prompt_text=prompt,
        correction_inbox=tmp_path / "cli-return.jsonl",
        output_log=tmp_path / "output.log",
        runtime_dir=tmp_path / ".atdd" / "runtime",
        env_overrides={},
        transport="cmux-native",
        permission_mode=mode,
        allowed_tools=tools,
    )


def test_seed_argv_places_prompt_before_variadic_allowedtools():
    """The positional prompt MUST precede --allowedTools (variadic would eat it)."""
    argv = build_agent_seed_argv("claude", "DO THE THING", permission_mode="acceptEdits",
                                 allowed_tools=("Read", "Edit"))
    assert argv[0] == "claude"
    assert argv[1] == "DO THE THING", "prompt must be the first positional"
    assert argv.index("DO THE THING") < argv.index("--allowedTools")
    assert argv[argv.index("--permission-mode") + 1] == "acceptEdits"
    assert argv[argv.index("--allowedTools") + 1] == "Read Edit"


def test_seed_argv_omits_allowedtools_when_empty():
    argv = build_agent_seed_argv("claude", "hi", permission_mode="default", allowed_tools=())
    assert "--allowedTools" not in argv


def test_cmux_launch_wraps_command_and_prompt_survives_shlex(tmp_path):
    agent_argv = build_agent_seed_argv("claude", "Work issue #978",
                                       permission_mode="acceptEdits", allowed_tools=("Read", "Edit"))
    launch = build_cmux_launch_argv(agent_argv, cwd=tmp_path, name="ATDD978")
    assert launch[:2] == ["cmux", "new-workspace"]
    assert launch[launch.index("--cwd") + 1] == str(tmp_path.resolve())
    command = launch[launch.index("--command") + 1]
    parsed = shlex.split(command)
    assert parsed[1] == "Work issue #978", "positional prompt survives the --command round-trip"
    assert parsed[parsed.index("--allowedTools") + 1] == "Read Edit"


def test_controller_spawn_delegates_to_cmux_runner_no_shim(tmp_path):
    """spawn() launches via the injected cmux runner with a prompt-first command and
    returns a cmux-native handle — no pty/shim, no cli-return inbox write."""
    calls = []
    ctl = CmuxAgentController(runner=lambda argv: calls.append(list(argv)) or "OK workspace:9")
    handle = ctl.spawn(_spec(tmp_path))

    assert handle.transport == "cmux-native"
    assert len(calls) == 1
    launch = calls[0]
    assert launch[:2] == ["cmux", "new-workspace"]
    command = launch[launch.index("--command") + 1]
    parsed = shlex.split(command)
    assert parsed[0] == "claude"
    assert parsed[1] == "Work issue #978"  # prompt-first seed
    assert "--dangerously-skip-permissions" not in command
    # no cli-return inbox was written (that's the shim path, not this one)
    assert not (tmp_path / "cli-return.jsonl").exists()


def test_controller_refuses_forbidden_flag(tmp_path):
    """A bypass flag smuggled in as an 'allowed tool' is refused at the launch boundary."""
    from atdd.runtime.agent_control import ForbiddenLaunchFlagError

    ctl = CmuxAgentController(runner=lambda argv: "")
    spec = _spec(tmp_path, tools=("Read", "--dangerously-skip-permissions"))
    with pytest.raises(ForbiddenLaunchFlagError):
        ctl.spawn(spec)


def test_controller_interrupt_uses_cmux_send_key(tmp_path):
    calls = []
    ctl = CmuxAgentController(runner=lambda argv: calls.append(list(argv)) or "")
    handle = ctl.spawn(_spec(tmp_path))
    calls.clear()
    ctl.signal(handle, AgentSignal.INTERRUPT)
    assert calls == [["cmux", "send-key", "C-c"]]
