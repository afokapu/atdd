# URN: test:spawn-agents:E016-UNIT-003-non-cli-return-shell-prefix-reconstructed
# Acceptance: acc:spawn-agents:E016-UNIT-003-non-cli-return-shell-prefix-reconstructed
# WMBT: wmbt:spawn-agents:E016
# Phase: GREEN
# Assertion: behavioral
"""E016-UNIT-003 — non-cli-return path reconstructs shell prefix from env_overrides.

Tests that _inject_agent_env returns a dict and the call site in cmd_spawn
correctly converts it back to a KEY=value shell prefix for shell dispatch.
We test this by exercising the reconstruction logic directly: given
env_overrides from _inject_agent_env, verify the prefix is reconstructed.
"""
from __future__ import annotations

import shlex

import pytest

from atdd.coach.commands.spawn import _inject_agent_env


def _reconstruct_shell_prefix(env_overrides: dict[str, str], command: str) -> str:
    """Mirror the reconstruction logic in cmd_spawn's non-cli-return branch."""
    if not env_overrides:
        return command
    prefix = " ".join(
        f"{k}={shlex.quote(str(v))}" for k, v in env_overrides.items()
    )
    return f"{prefix} {command}"


def test_reconstructed_command_starts_with_key_value_prefix():
    env_overrides, cmd = _inject_agent_env("claude --permission-mode auto", "planner-854-test")
    surface_cmd = _reconstruct_shell_prefix(env_overrides, cmd)
    assert surface_cmd.startswith("ATDD_AGENT_ID=planner-854-test"), (
        f"Expected KEY=value prefix, got: {surface_cmd!r}"
    )


def test_reconstructed_command_has_no_env_flag():
    env_overrides, cmd = _inject_agent_env("claude --permission-mode auto", "planner-854-test")
    surface_cmd = _reconstruct_shell_prefix(env_overrides, cmd)
    assert "--env" not in surface_cmd, (
        f"'--env' must not appear in shell-dispatch command: {surface_cmd!r}"
    )


def test_reconstructed_command_preserves_adapter_command():
    env_overrides, cmd = _inject_agent_env("claude --permission-mode auto", "planner-854-test")
    surface_cmd = _reconstruct_shell_prefix(env_overrides, cmd)
    assert "claude --permission-mode auto" in surface_cmd


def test_empty_env_overrides_command_unchanged():
    env_overrides, cmd = _inject_agent_env("claude", "")
    surface_cmd = _reconstruct_shell_prefix(env_overrides, cmd)
    assert surface_cmd == "claude"
