# URN: test:spawn-agents:isolate-worker-claude-config-dir:E030-UNIT-006-both-launch-planes-seed-before-emitting-config-dir
# Acceptance: acc:spawn-agents:E030-UNIT-006-both-launch-planes-seed-before-emitting-config-dir
# WMBT: wmbt:spawn-agents:E030
# Phase: GREEN
# Assertion: behavioral
"""E030-UNIT-006 — both worker launch planes seed the isolated
``CLAUDE_CONFIG_DIR`` through the ONE shared primitive before emitting it.

RED until both the cmux-native builder
(``cmux_launch.build_worker_launch_env``) and the legacy adapter
(``spawn.py::_inject_agent_env``) call ``seed_isolated_config_dir`` so NEITHER
plane can launch a worker against an empty, auth-less config dir. Closes the
#1066 regression on both surfaces, not just one — and the pre-existing E030
guarantees (config dir under the worktree runtime dir, ``ATDD_AGENT_ID``
injected, no ``--bare`` / ``CLAUDE_CODE_SIMPLE``) still hold.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.coder]

from atdd.coach.commands.spawn import _inject_agent_env
from atdd.runtime.agent_control.cmux_launch import (
    build_worker_launch_env,
    isolated_claude_config_dir,
)


def _fake_operator_root(tmp_path: Path) -> Path:
    root = tmp_path / "operator-claude"
    root.mkdir()
    (root / "settings.json").write_text('{"theme":"dark"}', encoding="utf-8")
    (root / ".credentials.json").write_text('{"token":"abc"}', encoding="utf-8")
    proj = root / "projects" / "-Users-x-atdd-main" / "memory"
    proj.mkdir(parents=True)
    (proj / "MEMORY.md").write_text("operator memory", encoding="utf-8")
    return root


def _assert_seeded(config_dir: Path) -> None:
    assert (config_dir / "settings.json").exists(), "auth/onboarding config not seeded"
    assert (config_dir / ".credentials.json").exists()
    assert not (config_dir / "projects").exists(), "projects/ must stay unseeded (#1057)"


def test_cmux_native_plane_seeds_before_emitting(tmp_path: Path):
    root = _fake_operator_root(tmp_path)
    worktree = tmp_path / "feat-issue-1066"
    worktree.mkdir()
    agent_id = "coder-1066-aaaa"

    env = build_worker_launch_env(agent_id, worktree, config_root=root)

    target = Path(env["CLAUDE_CONFIG_DIR"])
    assert target == isolated_claude_config_dir(agent_id, worktree)
    assert (worktree / ".atdd" / "runtime").resolve() in target.resolve().parents
    _assert_seeded(target)
    # no Feed-disabling lever smuggled in
    assert "CLAUDE_CODE_SIMPLE" not in env
    assert not any("bare" in k.lower() for k in env)


def test_legacy_adapter_plane_seeds_before_emitting(tmp_path: Path):
    root = _fake_operator_root(tmp_path)
    worktree = tmp_path / "feat-issue-1066"
    worktree.mkdir()
    agent_id = "tester-1066-bbbb"

    overrides, _cmd = _inject_agent_env(
        "claude --permission-mode acceptEdits",
        agent_id,
        worktree_root=worktree,
        config_root=root,
    )

    target = Path(overrides["CLAUDE_CONFIG_DIR"])
    assert target == isolated_claude_config_dir(agent_id, worktree)
    assert overrides["ATDD_AGENT_ID"] == agent_id
    _assert_seeded(target)
    assert "CLAUDE_CODE_SIMPLE" not in overrides


def test_both_planes_seed_the_same_target_identically(tmp_path: Path):
    """The two planes derive the SAME isolated target for a given (agent_id,
    worktree) and seed it the same way — one shared primitive, not two
    divergent implementations."""
    root = _fake_operator_root(tmp_path)
    worktree = tmp_path / "feat-issue-1066"
    worktree.mkdir()
    agent_id = "coder-1066-cccc"

    env = build_worker_launch_env(agent_id, worktree, config_root=root)
    overrides, _cmd = _inject_agent_env(
        "claude", agent_id, worktree_root=worktree, config_root=root
    )

    assert env["CLAUDE_CONFIG_DIR"] == overrides["CLAUDE_CONFIG_DIR"]
    target = Path(env["CLAUDE_CONFIG_DIR"])
    _assert_seeded(target)
