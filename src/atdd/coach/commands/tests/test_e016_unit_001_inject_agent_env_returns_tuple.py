"""E016-UNIT-001 — _inject_agent_env returns (env_overrides, command) tuple.

RED: fails until _inject_agent_env signature is changed.
"""
from __future__ import annotations

import pytest

from atdd.coach.commands.spawn import _inject_agent_env


def test_returns_tuple_with_env_override_when_agent_id_set():
    env_overrides, cmd = _inject_agent_env("claude --permission-mode auto", "planner-001-abc")
    assert env_overrides == {"ATDD_AGENT_ID": "planner-001-abc"}
    assert cmd == "claude --permission-mode auto"


def test_returns_empty_dict_when_agent_id_empty():
    env_overrides, cmd = _inject_agent_env("claude --permission-mode auto", "")
    assert env_overrides == {}
    assert cmd == "claude --permission-mode auto"


def test_command_unchanged_regardless_of_agent_id():
    adapter_cmd = "python3 -m atdd.coach.adapters.glm --yolo"
    env_overrides, cmd = _inject_agent_env(adapter_cmd, "coder-828-x")
    assert cmd == adapter_cmd
    assert env_overrides == {"ATDD_AGENT_ID": "coder-828-x"}


def test_agent_id_not_shell_quoted_into_command():
    """The env value must be in the dict — not shell-embedded in the command string."""
    env_overrides, cmd = _inject_agent_env("claude", "tester-001")
    assert "ATDD_AGENT_ID" not in cmd
    assert env_overrides.get("ATDD_AGENT_ID") == "tester-001"
