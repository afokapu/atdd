# URN: test:drive-state-machine:consolidate-worktree-command:E008-UNIT-003-dirty-tree-skips-fast-forward
# Acceptance: acc:drive-state-machine:E008-UNIT-003-dirty-tree-skips-fast-forward
# WMBT: wmbt:drive-state-machine:E008
# Phase: RED
# Harness: unit
# Layer: domain
"""E008-UNIT-003 — a dirty working tree skips the fast-forward (loud skip).

Issue #1347. Even when local ``main`` is cleanly behind ``origin/main``, if its
working tree has uncommitted changes ``_ff_sync_default_branch`` must skip rather
than move the checkout under the operator's feet.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atdd.coach.commands.branch import BranchManager

pytestmark = [pytest.mark.platform]


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True)


def _repo_behind_but_dirty(tmp_path: Path) -> Path:
    repo = tmp_path / "main"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "Tester")
    (repo / "f.txt").write_text("A\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "A")
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    _git(repo, "remote", "add", "origin", str(bare))
    _git(repo, "push", "origin", "main")
    (repo / "f.txt").write_text("A\nB\n")
    _git(repo, "commit", "-am", "B")
    _git(repo, "push", "origin", "main")
    _git(repo, "reset", "--hard", "HEAD~1")  # behind-only, clean
    (repo / "dirty.txt").write_text("uncommitted\n")  # now dirty
    return repo


def test_e008_unit_003_dirty_tree_skips_fast_forward(tmp_path, capsys):
    repo = _repo_behind_but_dirty(tmp_path)
    local_before = _git(repo, "rev-parse", "main").stdout.strip()

    BranchManager(repo)._ff_sync_default_branch("main")

    assert _git(repo, "rev-parse", "main").stdout.strip() == local_before  # no ff applied
    assert "dirty" in capsys.readouterr().out.lower()
