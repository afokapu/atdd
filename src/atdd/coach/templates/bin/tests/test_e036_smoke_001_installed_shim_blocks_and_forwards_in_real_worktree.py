# URN: test:govern-lifecycle:agnostic-git-config-bare-guard-via-path-shim:E036-SMOKE-001-installed-shim-blocks-and-forwards-in-real-worktree
# Acceptance: acc:govern-lifecycle:E036-SMOKE-001-installed-shim-blocks-and-forwards-in-real-worktree
# WMBT: wmbt:govern-lifecycle:E036
# Phase: RED
# Layer: backend.integration
"""AC-SMOKE-001: the on-disk git.shim, installed to .atdd/bin/git in a real git
worktree with a real PATH arrangement, blocks unscoped `git config core.bare
true` against the real shell PATH-resolution mechanism AND forwards a real
`git status` to the real git binary — proving an actual operator/agent shell
call is intercepted while the hot read-path survives.

RED state: src/atdd/coach/templates/bin/git.shim does not exist yet.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from atdd.coach.utils.repo import find_repo_root

pytestmark = [pytest.mark.coach]

REPO_ROOT = find_repo_root()
GIT_SHIM_TEMPLATE = REPO_ROOT / "src" / "atdd" / "coach" / "templates" / "bin" / "git.shim"


def test_real_worktree_shim_blocks_bare_and_forwards_status(tmp_path: Path) -> None:
    assert GIT_SHIM_TEMPLATE.exists(), (
        f"RED: git.shim template not implemented yet at {GIT_SHIM_TEMPLATE.relative_to(REPO_ROOT)}"
    )

    worktree = tmp_path / "repo"
    worktree.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(worktree)], check=True, capture_output=True)

    # Install the real shim to .atdd/bin/git.
    shim_dir = worktree / ".atdd" / "bin"
    shim_dir.mkdir(parents=True)
    shutil.copy(GIT_SHIM_TEMPLATE, shim_dir / "git")
    (shim_dir / "git").chmod(0o755)

    # The real system git resolves after the shim dir.
    real_git = shutil.which("git")
    assert real_git, "no real git on PATH for the smoke test"
    env = {**os.environ, "PATH": f"{shim_dir}:{os.environ.get('PATH', '')}"}

    # 1) Block path: unscoped core.bare write is hard-blocked, config untouched.
    blocked = subprocess.run(
        ["git", "config", "core.bare", "true"],
        cwd=str(worktree), env=env, capture_output=True, text=True, timeout=20,
    )
    assert blocked.returncode == 1, f"shim did not hard-block: exit {blocked.returncode}\n{blocked.stderr}"
    assert "--worktree" in blocked.stderr, f"alternative missing: {blocked.stderr!r}"

    # The shared config must NOT have been poisoned (read via the real git directly).
    effective = subprocess.run(
        [real_git, "config", "--get", "core.bare"],
        cwd=str(worktree), capture_output=True, text=True, timeout=20,
    )
    assert effective.stdout.strip().lower() != "true", "core.bare was poisoned despite the block"

    # 2) Forward path: a real `git status` is relayed to the real git and succeeds.
    status = subprocess.run(
        ["git", "status"],
        cwd=str(worktree), env=env, capture_output=True, text=True, timeout=20,
    )
    assert status.returncode == 0, f"git status was not forwarded to real git: {status.stderr!r}"
