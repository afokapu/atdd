# URN: test:spawn-agents:isolate-worker-claude-config-dir:E030-UNIT-002-cmux-native-launch-env-carries-isolated-config-dir
# Acceptance: acc:spawn-agents:E030-UNIT-002-cmux-native-launch-env-carries-isolated-config-dir
# WMBT: wmbt:spawn-agents:E030
# Phase: GREEN
# Assertion: behavioral
"""E030-UNIT-002 — the cmux-native launch plane (``cmux_launch.py``) carries
``CLAUDE_CONFIG_DIR`` set to the per-worker isolated path.

RED: fails until ``cmux_launch`` grows a pure worker-env builder
(``build_worker_launch_env(agent_id, worktree_root)``) that injects
``CLAUDE_CONFIG_DIR`` = the AC-UNIT-001 isolated path into the surface launch env.
The Feed hooks must remain active — NO ``--bare`` flag and NO ``CLAUDE_CODE_SIMPLE``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.coder]

from atdd.runtime.agent_control.cmux_launch import (
    build_agent_seed_argv,
    build_worker_launch_env,
    isolated_claude_config_dir,
)


def test_launch_env_defines_claude_config_dir(tmp_path: Path):
    worktree = tmp_path / "feat-spawned-workers-1057"
    worktree.mkdir()
    env = build_worker_launch_env("planner-1057-ebbc5293", worktree)

    assert "CLAUDE_CONFIG_DIR" in env, (
        "cmux-native launch env must define CLAUDE_CONFIG_DIR"
    )


def test_claude_config_dir_equals_the_single_source_derivation(tmp_path: Path):
    worktree = tmp_path / "feat-spawned-workers-1057"
    worktree.mkdir()
    agent_id = "planner-1057-ebbc5293"
    env = build_worker_launch_env(agent_id, worktree)

    expected = str(isolated_claude_config_dir(agent_id, worktree))
    assert env["CLAUDE_CONFIG_DIR"] == expected, (
        "cmux-native CLAUDE_CONFIG_DIR must equal the one-source-of-truth derivation"
    )


def test_claude_config_dir_is_not_operator_dir(tmp_path: Path):
    worktree = tmp_path / "feat-spawned-workers-1057"
    worktree.mkdir()
    env = build_worker_launch_env("coder-1057-aa11", worktree)
    value = Path(env["CLAUDE_CONFIG_DIR"]).resolve()

    operator_default = (Path.home() / ".claude").resolve()
    assert value != operator_default
    assert operator_default not in value.parents
    assert "atdd/main/.git" not in str(value)


def test_no_bare_and_no_simple_flag_feed_hooks_preserved(tmp_path: Path):
    worktree = tmp_path / "feat-spawned-workers-1057"
    worktree.mkdir()
    env = build_worker_launch_env("tester-1057-d9c9ea70", worktree)

    # The env-override mechanism must not smuggle in a Feed-disabling lever.
    assert "CLAUDE_CODE_SIMPLE" not in env, (
        "CLAUDE_CODE_SIMPLE would disable hooks — Feed publishing must stay active"
    )

    argv = build_agent_seed_argv(
        "claude",
        "Work issue #1057",
        permission_mode="acceptEdits",
        allowed_tools=("Read", "Edit"),
    )
    assert "--bare" not in argv, (
        "--bare disables the cmux Feed-publishing hooks — explicitly rejected (Decision #2)"
    )
