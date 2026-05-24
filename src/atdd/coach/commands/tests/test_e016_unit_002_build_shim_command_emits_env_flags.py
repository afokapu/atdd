"""E016-UNIT-002 — _build_shim_command emits --env KEY=VALUE flags instead of shell prefix.

RED: fails until _build_shim_command accepts env_overrides and emits --env flags.
"""
from __future__ import annotations

import shlex
from pathlib import Path

import pytest

from atdd.coach.commands.spawn import _build_shim_command


def test_env_flag_emitted_before_separator():
    cmd = _build_shim_command(
        "claude --permission-mode auto",
        "planner-001-abc",
        Path("/tmp/runtime"),
        env_overrides={"ATDD_AGENT_ID": "planner-001-abc"},
    )
    assert "--env ATDD_AGENT_ID=planner-001-abc" in cmd


def test_adapter_command_is_argv0_after_separator():
    cmd = _build_shim_command(
        "claude --permission-mode auto",
        "planner-001",
        Path("/tmp/runtime"),
        env_overrides={"ATDD_AGENT_ID": "planner-001"},
    )
    tokens = shlex.split(cmd)
    sep_idx = tokens.index("--")
    assert tokens[sep_idx + 1] == "claude", (
        f"Expected 'claude' as argv[0] after '--', got {tokens[sep_idx + 1]!r}"
    )


def test_shell_prefix_not_in_argv_after_separator():
    cmd = _build_shim_command(
        "claude --permission-mode auto",
        "x-001",
        Path("/tmp/runtime"),
        env_overrides={"ATDD_AGENT_ID": "x-001"},
    )
    tokens = shlex.split(cmd)
    sep_idx = tokens.index("--")
    after_sep = tokens[sep_idx + 1 :]
    for tok in after_sep:
        assert not tok.startswith("ATDD_AGENT_ID="), (
            f"Shell-style env prefix '{tok}' must not appear after '--' in argv"
        )


def test_empty_env_overrides_no_env_flag():
    cmd = _build_shim_command(
        "claude",
        "x-001",
        Path("/tmp/runtime"),
        env_overrides={},
    )
    assert "--env" not in cmd


def test_multiple_env_overrides_all_emitted():
    cmd = _build_shim_command(
        "claude",
        "x-001",
        Path("/tmp/runtime"),
        env_overrides={"ATDD_AGENT_ID": "x-001", "ATDD_LLM": "claude-code"},
    )
    assert "--env ATDD_AGENT_ID=x-001" in cmd
    assert "--env ATDD_LLM=claude-code" in cmd
