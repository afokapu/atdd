# URN: test:spawn-agents:E017-UNIT-001-build-shim-command-uses-module-invocation
# Acceptance: acc:spawn-agents:E017-UNIT-001-build-shim-command-uses-module-invocation
# WMBT: wmbt:spawn-agents:E017
# Phase: GREEN
# Assertion: behavioral
"""E017-UNIT-001 — _build_shim_command uses module-invocation form (sys.executable -m atdd.coach.shim)
instead of a bare 'atdd-shim' token, eliminating PATH resolution on multi-install hosts.

RED: fails until _build_shim_command uses sys.executable as the first argv element.
"""
from __future__ import annotations

import shlex
import sys
from pathlib import Path

import pytest

from atdd.coach.commands.spawn import _build_shim_command


def test_first_token_is_sys_executable():
    cmd = _build_shim_command(
        "claude --permission-mode auto",
        "planner-857-abc",
        Path("/tmp/runtime"),
        env_overrides={},
    )
    tokens = shlex.split(cmd)
    assert tokens[0] == sys.executable, (
        f"Expected first token to be sys.executable={sys.executable!r}, "
        f"got {tokens[0]!r} — bare 'atdd-shim' token is not acceptable on multi-install hosts"
    )


def test_module_flag_follows_executable():
    cmd = _build_shim_command(
        "claude --permission-mode auto",
        "planner-857-abc",
        Path("/tmp/runtime"),
        env_overrides={},
    )
    tokens = shlex.split(cmd)
    assert len(tokens) >= 2, "Command must have at least 2 tokens (executable + -m)"
    assert tokens[1] == "-m", (
        f"Expected second token '-m' (module-invocation form), got {tokens[1]!r}"
    )


def test_module_specifier_is_atdd_coach_shim():
    cmd = _build_shim_command(
        "claude --permission-mode auto",
        "planner-857-abc",
        Path("/tmp/runtime"),
        env_overrides={},
    )
    tokens = shlex.split(cmd)
    assert len(tokens) >= 3, "Command must have at least 3 tokens"
    assert tokens[2] == "atdd.coach.shim", (
        f"Expected module specifier 'atdd.coach.shim', got {tokens[2]!r}"
    )
