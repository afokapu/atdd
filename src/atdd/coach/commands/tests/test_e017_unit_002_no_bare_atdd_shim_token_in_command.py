# URN: test:spawn-agents:E017-UNIT-002-no-bare-atdd-shim-token-in-command
# Acceptance: acc:spawn-agents:E017-UNIT-002-no-bare-atdd-shim-token-in-command
# WMBT: wmbt:spawn-agents:E017
# Phase: GREEN
# Assertion: behavioral
"""E017-UNIT-002 — even when PATH puts a stale homebrew atdd-shim first, _build_shim_command
uses sys.executable and does not contain the bare string 'atdd-shim' as a token.

RED: fails until _build_shim_command removes the bare 'atdd-shim' token.
"""
from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path

import pytest

from atdd.coach.commands.spawn import _build_shim_command


def test_bare_atdd_shim_not_in_command():
    cmd = _build_shim_command(
        "claude --permission-mode auto",
        "planner-857-xyz",
        Path("/tmp/runtime"),
        env_overrides={},
    )
    tokens = shlex.split(cmd)
    assert "atdd-shim" not in tokens, (
        f"Bare 'atdd-shim' token must not appear in command — it is PATH-resolved "
        f"and picks up the wrong installation on multi-install hosts. Got: {tokens!r}"
    )


def test_uses_sys_executable_regardless_of_path(monkeypatch):
    """Even when PATH is manipulated to put a different installation first,
    _build_shim_command still uses sys.executable."""
    monkeypatch.setenv("PATH", "/opt/homebrew/bin:/usr/local/bin:" + os.environ.get("PATH", ""))
    cmd = _build_shim_command(
        "claude",
        "planner-857-path-test",
        Path("/tmp/rt"),
        env_overrides={},
    )
    tokens = shlex.split(cmd)
    assert tokens[0] == sys.executable, (
        f"Expected {sys.executable!r} as first token even with manipulated PATH, "
        f"got {tokens[0]!r}"
    )


def test_atdd_coach_shim_string_present_in_command():
    cmd = _build_shim_command(
        "claude",
        "tester-857-abc",
        Path("/tmp/rt"),
        env_overrides={},
    )
    assert "atdd.coach.shim" in cmd, (
        f"Command must contain module specifier 'atdd.coach.shim', got: {cmd!r}"
    )
