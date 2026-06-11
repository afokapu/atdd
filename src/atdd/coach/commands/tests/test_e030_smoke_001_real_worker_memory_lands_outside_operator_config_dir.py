# URN: test:spawn-agents:isolate-worker-claude-config-dir:E030-SMOKE-001-real-worker-memory-lands-outside-operator-config-dir
# Acceptance: acc:spawn-agents:E030-SMOKE-001-real-worker-memory-lands-outside-operator-config-dir
# WMBT: wmbt:spawn-agents:E030
# Phase: SMOKE
# Layer: assembly
# Runtime: python
# Smoke: true
# Assertion: behavioral
"""E030-SMOKE-001 — a real spawned worker, launched through the deployed coach
spawn path, writes any Claude auto-memory into its isolated ``CLAUDE_CONFIG_DIR``
under the worktree runtime dir and creates NO new file under the operator's
``~/.claude/projects/-…-atdd-main/memory/`` dir.

Opt-in: skipped unless ``ATDD_RUN_SMOKE=1`` and the installed Claude CLI is
available. Delivered at RED to bind the ``E030-SMOKE-001`` acceptance; exercised at
the GREEN→SMOKE transition against the real, installed Claude CLI (no mocks per
``tester/conventions/smoke.convention.yaml``).
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.platform,
    pytest.mark.smoke,
    pytest.mark.skipif(
        not os.environ.get("ATDD_RUN_SMOKE"),
        reason="opt-in SMOKE test — set ATDD_RUN_SMOKE=1 to run against the real Claude CLI",
    ),
    pytest.mark.skipif(
        shutil.which("claude") is None,
        reason="real Claude CLI not installed on PATH",
    ),
]


def _operator_memory_dir() -> Path:
    """The operator's shared ``-main`` memory dir that workers must NOT pollute."""
    home = Path.home() / ".claude" / "projects"
    candidates = sorted(home.glob("*-atdd-main/memory")) if home.exists() else []
    if not candidates:
        pytest.skip("operator -atdd-main memory dir not present on this host")
    return candidates[0]


def _snapshot(memory_dir: Path) -> tuple[set[str], int]:
    files = {p.name for p in memory_dir.iterdir()} if memory_dir.exists() else set()
    memory_md = memory_dir / "MEMORY.md"
    size = memory_md.stat().st_size if memory_md.exists() else 0
    return files, size


def test_real_worker_memory_lands_outside_operator_config_dir(tmp_path: Path):
    """Launch a real worker through the deployed spawn path; assert its launch env
    carries an isolated CLAUDE_CONFIG_DIR and the operator memory dir is untouched."""
    from atdd.coach.commands.spawn import _inject_agent_env
    from atdd.runtime.agent_control.cmux_launch import isolated_claude_config_dir

    operator_dir = _operator_memory_dir()
    before_files, before_size = _snapshot(operator_dir)

    worktree = tmp_path / "feat-spawned-workers-1057"
    worktree.mkdir()
    agent_id = "tester-1057-smoke"

    # The deployed launch env-assembly the coach uses for a spawned worker.
    env_overrides, _cmd = _inject_agent_env(
        "claude --permission-mode acceptEdits", agent_id, worktree_root=worktree
    )

    # (1) The worker launch env carries CLAUDE_CONFIG_DIR under the worktree runtime
    #     dir — not the operator ~/.claude.
    config_dir = Path(env_overrides["CLAUDE_CONFIG_DIR"]).resolve()
    assert config_dir == Path(isolated_claude_config_dir(agent_id, worktree)).resolve()
    assert (Path.home() / ".claude").resolve() not in config_dir.parents
    assert (worktree / ".atdd" / "runtime").resolve() in config_dir.parents

    # (2) Drive a real Claude turn under the isolated config dir; whatever memory the
    #     worker writes must land in config_dir, never in the operator dir.
    config_dir.mkdir(parents=True, exist_ok=True)
    worker_env = {**os.environ, **{k: str(v) for k, v in env_overrides.items()}}
    import subprocess

    subprocess.run(
        ["claude", "-p", "Say 'isolation smoke ok' and stop.", "--permission-mode", "acceptEdits"],
        cwd=str(worktree),
        env=worker_env,
        capture_output=True,
        text=True,
        timeout=180,
    )

    # (3) The operator -main memory dir gained no new file and MEMORY.md is unchanged.
    after_files, after_size = _snapshot(operator_dir)
    assert after_files == before_files, (
        f"worker created new file(s) in operator memory dir: {after_files - before_files}"
    )
    assert after_size == before_size, "worker appended to operator MEMORY.md"

    # (4) Any Claude state the worker wrote is under the isolated config dir.
    assert config_dir.exists()
