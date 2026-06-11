# URN: test:spawn-agents:isolate-worker-claude-config-dir:E030-UNIT-001-isolated-config-dir-derivation
# Acceptance: acc:spawn-agents:E030-UNIT-001-isolated-config-dir-derivation
# WMBT: wmbt:spawn-agents:E030
# Phase: GREEN
# Assertion: behavioral
"""E030-UNIT-001 — single pure derivation of the per-worker isolated
``CLAUDE_CONFIG_DIR`` path.

RED: fails until ``isolated_claude_config_dir(agent_id, worktree_root)`` exists in
``atdd.runtime.agent_control.cmux_launch``. The derivation is the ONE source of
truth both launch sites consume; it must return a path UNDER the issue worktree's
``.atdd/runtime`` subtree and NEVER under the operator's ``~/.claude`` config dir
(whose git-common-dir resolves to ``…/atdd/main/.git`` → the polluted ``-main``
memory dir).
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.coder]

from atdd.runtime.agent_control.cmux_launch import isolated_claude_config_dir


def test_path_is_under_worktree_atdd_runtime_subtree(tmp_path: Path):
    worktree = tmp_path / "feat-spawned-workers-1057"
    worktree.mkdir()
    derived = Path(isolated_claude_config_dir("planner-1057-ebbc5293", worktree))

    runtime_root = (worktree / ".atdd" / "runtime").resolve()
    assert runtime_root in derived.resolve().parents, (
        f"isolated config dir {derived} is not under the worktree runtime subtree "
        f"{runtime_root}"
    )


def test_path_carries_the_agent_id_segment(tmp_path: Path):
    worktree = tmp_path / "feat-spawned-workers-1057"
    worktree.mkdir()
    agent_id = "tester-1057-d9c9ea70"
    derived = Path(isolated_claude_config_dir(agent_id, worktree))

    assert agent_id in derived.parts, (
        f"isolated config dir {derived} does not carry the agent_id {agent_id!r} "
        "as a path segment (per-worker isolation)"
    )


def test_path_is_not_the_operator_default_config_dir(tmp_path: Path):
    worktree = tmp_path / "feat-spawned-workers-1057"
    worktree.mkdir()
    derived = Path(isolated_claude_config_dir("coder-1057-aa11", worktree)).resolve()

    operator_default = (Path.home() / ".claude").resolve()
    assert derived != operator_default
    assert operator_default not in derived.parents, (
        f"isolated config dir {derived} is a descendant of the operator default "
        f"{operator_default} — auto-memory would bleed back into the operator dir"
    )


def test_path_never_references_main_git_common_dir(tmp_path: Path):
    worktree = tmp_path / "feat-spawned-workers-1057"
    worktree.mkdir()
    derived = str(isolated_claude_config_dir("planner-1057-ebbc5293", worktree))

    assert "atdd/main/.git" not in derived, (
        "isolated config dir must not reference the shared git-common-dir "
        f"(…/atdd/main/.git) — got {derived}"
    )
    assert not derived.rstrip("/").endswith("-main/memory"), (
        f"isolated config dir must not land in the operator -main memory dir: {derived}"
    )


def test_two_agents_derive_distinct_paths_no_collision(tmp_path: Path):
    worktree = tmp_path / "feat-spawned-workers-1057"
    worktree.mkdir()
    a = Path(isolated_claude_config_dir("planner-1057-ebbc5293", worktree)).resolve()
    b = Path(isolated_claude_config_dir("tester-1057-d9c9ea70", worktree)).resolve()

    assert a != b, "distinct agent_ids must derive distinct isolated config dirs"


def test_derivation_is_deterministic(tmp_path: Path):
    worktree = tmp_path / "feat-spawned-workers-1057"
    worktree.mkdir()
    first = Path(isolated_claude_config_dir("coder-1057-aa11", worktree)).resolve()
    second = Path(isolated_claude_config_dir("coder-1057-aa11", worktree)).resolve()

    assert first == second, "same (agent_id, worktree) must derive the same path"
