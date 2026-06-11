# URN: test:spawn-agents:isolate-worker-claude-config-dir:E030-UNIT-003-legacy-adapter-launch-env-carries-isolated-config-dir
# Acceptance: acc:spawn-agents:E030-UNIT-003-legacy-adapter-launch-env-carries-isolated-config-dir
# WMBT: wmbt:spawn-agents:E030
# Phase: GREEN
# Assertion: behavioral
"""E030-UNIT-003 — the legacy/headless adapter plane
(``spawn.py::_inject_agent_env`` → ``_prepend_env_prefix`` feeding
``_claude_code_adapter``) carries ``CLAUDE_CONFIG_DIR`` set to the SAME per-worker
isolated path as the cmux-native plane (one source of truth), while preserving the
pre-existing ``ATDD_AGENT_ID`` injection.

RED: fails until ``_inject_agent_env`` learns the worktree root and adds
``CLAUDE_CONFIG_DIR`` (from ``isolated_claude_config_dir``) to ``env_overrides``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.coder]

from atdd.coach.commands.spawn import _inject_agent_env
from atdd.runtime.agent_control.cmux_launch import isolated_claude_config_dir


def test_env_overrides_define_claude_config_dir(tmp_path: Path):
    worktree = tmp_path / "feat-spawned-workers-1057"
    worktree.mkdir()
    env_overrides, _cmd = _inject_agent_env(
        "claude --permission-mode acceptEdits", "coder-1057-aa11", worktree_root=worktree
    )

    assert "CLAUDE_CONFIG_DIR" in env_overrides, (
        "legacy adapter env_overrides must define CLAUDE_CONFIG_DIR"
    )


def test_claude_config_dir_equals_single_source_derivation(tmp_path: Path):
    worktree = tmp_path / "feat-spawned-workers-1057"
    worktree.mkdir()
    agent_id = "coder-1057-aa11"
    env_overrides, _cmd = _inject_agent_env(
        "claude --permission-mode acceptEdits", agent_id, worktree_root=worktree
    )

    expected = str(isolated_claude_config_dir(agent_id, worktree))
    assert env_overrides["CLAUDE_CONFIG_DIR"] == expected, (
        "legacy adapter CLAUDE_CONFIG_DIR must equal the same derivation the "
        "cmux-native plane uses (one source of truth)"
    )


def test_claude_config_dir_is_not_operator_dir(tmp_path: Path):
    worktree = tmp_path / "feat-spawned-workers-1057"
    worktree.mkdir()
    env_overrides, _cmd = _inject_agent_env(
        "claude --permission-mode acceptEdits", "coder-1057-aa11", worktree_root=worktree
    )
    value = Path(env_overrides["CLAUDE_CONFIG_DIR"]).resolve()

    operator_default = (Path.home() / ".claude").resolve()
    assert value != operator_default
    assert operator_default not in value.parents
    assert "atdd/main/.git" not in str(value)


def test_atdd_agent_id_injection_is_preserved(tmp_path: Path):
    """The new CLAUDE_CONFIG_DIR override must sit ALONGSIDE the pre-existing
    ATDD_AGENT_ID injection (#731 / #854), not replace it."""
    worktree = tmp_path / "feat-spawned-workers-1057"
    worktree.mkdir()
    env_overrides, _cmd = _inject_agent_env(
        "claude --permission-mode acceptEdits", "tester-1057-d9c9ea70", worktree_root=worktree
    )

    assert env_overrides.get("ATDD_AGENT_ID") == "tester-1057-d9c9ea70"
    assert "CLAUDE_CONFIG_DIR" in env_overrides
