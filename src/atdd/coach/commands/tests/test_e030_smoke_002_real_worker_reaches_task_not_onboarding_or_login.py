# URN: test:spawn-agents:isolate-worker-claude-config-dir:E030-SMOKE-002-real-worker-reaches-task-not-onboarding-or-login
# Acceptance: acc:spawn-agents:E030-SMOKE-002-real-worker-reaches-task-not-onboarding-or-login
# WMBT: wmbt:spawn-agents:E030
# Phase: SMOKE
# Layer: assembly
# Runtime: python
# Smoke: true
# Assertion: behavioral
"""E030-SMOKE-002 — a real spawned worker, launched through the deployed coach
spawn path with a SEEDED isolated ``CLAUDE_CONFIG_DIR``, actually REACHES its
task: it produces task output and does NOT park on Claude Code's first-run
onboarding ('Choose the text style' / 'Welcome to Claude Code') or the 'Select
login method' prompt — while STILL creating no new file under the operator
memory dir (#1057 guarantee preserved end-to-end).

This strengthens E030-SMOKE-001, which only proved the operator memory dir stays
clean and so passed even when the worker died at the login screen (#1066).

Opt-in: skipped unless ``ATDD_RUN_SMOKE=1`` and the installed, authenticated
Claude CLI is available.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.platform,
    pytest.mark.smoke,
    pytest.mark.skipif(
        not os.environ.get("ATDD_RUN_SMOKE"),
        reason="opt-in SMOKE test — set ATDD_RUN_SMOKE=1 to run against the real Claude CLI",
    ),
]

_ONBOARDING_MARKERS = (
    "Choose the text style",
    "Welcome to Claude Code",
    "Select login method",
    "Claude account with subscription",
)


def _operator_memory_dir() -> Path:
    home = Path.home() / ".claude" / "projects"
    candidates = sorted(home.glob("*-atdd-main/memory")) if home.exists() else []
    if not candidates:
        pytest.skip("operator -atdd-main memory dir not present on this host")
    return candidates[0]


def _snapshot(memory_dir: Path) -> tuple[set[str], int]:
    files = {p.name for p in memory_dir.iterdir()} if memory_dir.exists() else set()
    memory_md = memory_dir / "MEMORY.md"
    return files, (memory_md.stat().st_size if memory_md.exists() else 0)


def test_real_worker_reaches_task_not_onboarding_or_login(tmp_path: Path):
    import shutil

    if shutil.which("claude") is None:
        pytest.skip("real Claude CLI not installed on PATH")

    from atdd.coach.commands.spawn import _inject_agent_env
    from atdd.runtime.agent_control.cmux_launch import isolated_claude_config_dir

    operator_dir = _operator_memory_dir()
    before_files, before_size = _snapshot(operator_dir)

    worktree = tmp_path / "feat-issue-1066"
    worktree.mkdir()
    agent_id = "tester-1066-smoke"

    # Deployed launch env-assembly: this SEEDS the isolated CLAUDE_CONFIG_DIR.
    env_overrides, _cmd = _inject_agent_env(
        "claude --permission-mode acceptEdits", agent_id, worktree_root=worktree
    )
    config_dir = Path(env_overrides["CLAUDE_CONFIG_DIR"]).resolve()

    # (1) the target is under the worktree runtime dir and was SEEDED (not empty):
    #     the operator's auth/onboarding/settings resolve inside it.
    assert config_dir == isolated_claude_config_dir(agent_id, worktree).resolve()
    assert (Path.home() / ".claude").resolve() not in config_dir.parents
    assert any(config_dir.iterdir()), "isolated config dir was not seeded (empty)"
    assert not (config_dir / "projects").exists(), "projects/ must stay unseeded (#1057)"

    worker_env = {**os.environ, **{k: str(v) for k, v in env_overrides.items()}}
    result = subprocess.run(
        ["claude", "-p", "Reply with exactly: isolation seed ok", "--permission-mode", "acceptEdits"],
        cwd=str(worktree),
        env=worker_env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    combined = f"{result.stdout}\n{result.stderr}"

    # (2) the worker reached its task: produced output, no onboarding/login screen.
    for marker in _ONBOARDING_MARKERS:
        assert marker not in combined, (
            f"worker parked on onboarding/login (saw {marker!r}) — seed did not carry "
            f"auth/onboarding. Output:\n{combined[:500]}"
        )
    assert result.stdout.strip(), "worker produced no task output (did not reach its task)"

    # (3) the operator -main memory dir gained no new file (the #1057 guarantee holds).
    after_files, after_size = _snapshot(operator_dir)
    assert after_files == before_files, (
        f"worker created new file(s) in operator memory dir: {after_files - before_files}"
    )
    assert after_size == before_size, "worker appended to operator MEMORY.md"
