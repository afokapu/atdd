# URN: test:spawn-agents:E017-UNIT-003-module-invocation-passes-all-existing-args
# Acceptance: acc:spawn-agents:E017-UNIT-003-module-invocation-passes-all-existing-args
# WMBT: wmbt:spawn-agents:E017
# Phase: GREEN
# Assertion: behavioral
"""E017-UNIT-003 — the module-invocation form preserves all _build_shim_command arguments:
--agent-id, --runtime-dir, --env flags (E016), and the adapter command after '--'.

RED: fails until _build_shim_command uses sys.executable -m atdd.coach.shim with all args.
"""
from __future__ import annotations

import shlex
import sys
from pathlib import Path

import pytest

from atdd.coach.commands.spawn import _build_shim_command


def test_agent_id_flag_preserved():
    cmd = _build_shim_command(
        "claude --permission-mode auto",
        "planner-857-abc",
        Path("/tmp/rt"),
        env_overrides={"ATDD_AGENT_ID": "planner-857-abc"},
    )
    tokens = shlex.split(cmd)
    assert "--agent-id" in tokens, f"--agent-id flag missing from command: {tokens!r}"
    agent_id_idx = tokens.index("--agent-id")
    assert tokens[agent_id_idx + 1] == "planner-857-abc", (
        f"--agent-id value wrong: {tokens[agent_id_idx + 1]!r}"
    )


def test_runtime_dir_flag_preserved():
    cmd = _build_shim_command(
        "claude",
        "coder-857-001",
        Path("/tmp/my-runtime"),
        env_overrides={},
    )
    tokens = shlex.split(cmd)
    assert "--runtime-dir" in tokens, f"--runtime-dir flag missing: {tokens!r}"
    rt_idx = tokens.index("--runtime-dir")
    assert tokens[rt_idx + 1] == "/tmp/my-runtime", (
        f"--runtime-dir value wrong: {tokens[rt_idx + 1]!r}"
    )


def test_env_flag_preserved_after_module_invocation():
    cmd = _build_shim_command(
        "claude --permission-mode auto",
        "planner-857-abc",
        Path("/tmp/rt"),
        env_overrides={"ATDD_AGENT_ID": "planner-857-abc"},
    )
    tokens = shlex.split(cmd)
    # Check sys.executable is still first token (module form)
    assert tokens[0] == sys.executable, (
        f"First token must be sys.executable, got {tokens[0]!r}"
    )
    # --env flag must still be present (E016 requirement)
    assert "--env" in tokens, f"--env flag missing from command: {tokens!r}"
    env_idx = tokens.index("--env")
    assert tokens[env_idx + 1] == "ATDD_AGENT_ID=planner-857-abc", (
        f"--env value wrong: {tokens[env_idx + 1]!r}"
    )


def test_adapter_command_after_separator():
    cmd = _build_shim_command(
        "claude --permission-mode auto",
        "planner-857-abc",
        Path("/tmp/rt"),
        env_overrides={"ATDD_AGENT_ID": "planner-857-abc"},
    )
    tokens = shlex.split(cmd)
    assert "--" in tokens, f"'--' separator missing from command: {tokens!r}"
    sep_idx = tokens.index("--")
    after_sep = tokens[sep_idx + 1:]
    assert "claude" in after_sep, (
        f"Expected 'claude' after '--', got {after_sep!r}"
    )
    # The adapter command must not start with 'ATDD_AGENT_ID=' (E016 preserved)
    assert not after_sep[0].startswith("ATDD_AGENT_ID="), (
        f"Shell-style env prefix must not appear after '--', got {after_sep[0]!r}"
    )
