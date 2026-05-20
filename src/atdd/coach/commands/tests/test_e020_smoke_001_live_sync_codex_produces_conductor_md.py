# URN: test:govern-lifecycle:rename-codex-conductor-md:E020-SMOKE-001-live-sync-codex-produces-conductor-md
# Acceptance: acc:govern-lifecycle:E020-SMOKE-001-live-sync-codex-produces-conductor-md
# WMBT: wmbt:govern-lifecycle:E020
# Phase: SMOKE
# Layer: backend.smoke
"""
AC-SMOKE-001: Running `atdd sync --agent codex` against a live repo root
creates CONDUCTOR.md and does NOT create AGENTS.md.

RED state: The installed CLI writes AGENTS.md for codex. This test fails
until the CLI's AGENT_FILES["codex"] mapping is updated to "CONDUCTOR.md".
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


def _repo_root() -> Path:
    here = Path(__file__)
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


def _src_path() -> str:
    return str(_repo_root() / "src")


@pytest.mark.smoke
def test_live_sync_codex_creates_conductor_md(tmp_path: Path) -> None:
    """atdd sync --agent codex must create CONDUCTOR.md and not AGENTS.md."""
    atdd_dir = tmp_path / ".atdd"
    atdd_dir.mkdir()
    (atdd_dir / "config.yaml").write_text("sync:\n  agents:\n    - codex\n")

    env = os.environ.copy()
    env["PYTHONPATH"] = _src_path() + os.pathsep + env.get("PYTHONPATH", "")

    result = subprocess.run(
        [sys.executable, "-m", "atdd", "sync", "--agent", "codex"],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        env=env,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, f"atdd sync --agent codex exited {result.returncode}:\n{output}"
    assert (tmp_path / "CONDUCTOR.md").exists(), (
        f"CONDUCTOR.md not created; output:\n{output}"
    )
    assert not (tmp_path / "AGENTS.md").exists(), (
        f"AGENTS.md must not be created for codex; output:\n{output}"
    )
