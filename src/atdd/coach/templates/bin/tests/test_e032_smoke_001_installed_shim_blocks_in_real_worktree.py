# URN: test:govern-lifecycle:gh-issue-create-block-l3:E032-SMOKE-001-installed-shim-blocks-in-real-worktree
# Acceptance: acc:govern-lifecycle:E032-SMOKE-001-installed-shim-blocks-in-real-worktree
# WMBT: wmbt:govern-lifecycle:E032
# Phase: RED
# Layer: backend.integration
"""AC-SMOKE-001: the on-disk shim, installed in a real git worktree with a real
PATH arrangement, blocks `gh issue create` via the real shell PATH-resolution
mechanism — no recording stub for the block path, proving an actual operator
shell call is intercepted.

RED state: src/atdd/coach/templates/bin/gh.shim does not exist yet, so the shim
cannot be installed and the block cannot occur.
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
SHIM_TEMPLATE = REPO_ROOT / "src" / "atdd" / "coach" / "templates" / "bin" / "gh.shim"


def test_real_worktree_shim_blocks_issue_create(tmp_path: Path) -> None:
    assert SHIM_TEMPLATE.exists(), (
        f"RED: gh.shim template not implemented yet at {SHIM_TEMPLATE.relative_to(REPO_ROOT)}"
    )

    worktree = tmp_path / "repo"
    worktree.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(worktree)], check=True, capture_output=True)

    # Install the real shim to .atdd/bin/gh.
    shim_dir = worktree / ".atdd" / "bin"
    shim_dir.mkdir(parents=True)
    shutil.copy(SHIM_TEMPLATE, shim_dir / "gh")
    (shim_dir / "gh").chmod(0o755)

    # A real second gh on PATH after the shim dir (a downstream that would be
    # reached if the shim failed to block).
    downstream = tmp_path / "downstream"
    downstream.mkdir()
    (downstream / "gh").write_text("#!/bin/sh\necho 'DOWNSTREAM GH REACHED' >&2\nexit 0\n")
    (downstream / "gh").chmod(0o755)

    env = {**os.environ, "PATH": f"{shim_dir}:{downstream}:{os.environ.get('PATH', '')}"}
    result = subprocess.run(
        ["gh", "issue", "create", "--title", "real-smoke"],
        cwd=str(worktree),
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 1, f"shim did not hard-block: exit {result.returncode}\n{result.stderr}"
    assert "atdd issue" in result.stderr, f"alternative missing: {result.stderr!r}"
    assert "DOWNSTREAM GH REACHED" not in result.stderr, "downstream gh was reached despite the block"
