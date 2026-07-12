# URN: test:drive-state-machine:consolidate-worktree-command:E008-UNIT-001-behind-only-clean-fast-forwards-main
# Acceptance: acc:drive-state-machine:E008-UNIT-001-behind-only-clean-fast-forwards-main
# WMBT: wmbt:drive-state-machine:E008
# Phase: RED
# Harness: unit
# Layer: domain
"""E008-UNIT-001 — a clean behind-only default branch is fast-forwarded to origin.

Issue #1347. When local ``main`` is a proper ancestor of ``origin/main``
(behind-only, 0 ahead) with a clean working tree, ``_ff_sync_default_branch``
fast-forwards it — the ref advances to the exact origin commit, no merge commit.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atdd.coach.commands.branch import BranchManager

pytestmark = [pytest.mark.platform]


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True)


def _repo_behind_origin(tmp_path: Path) -> Path:
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
    # advance origin one commit, then rewind local main so it is behind-only
    (repo / "f.txt").write_text("A\nB\n")
    _git(repo, "commit", "-am", "B")
    _git(repo, "push", "origin", "main")
    _git(repo, "reset", "--hard", "HEAD~1")
    return repo


def test_e008_unit_001_behind_only_clean_fast_forwards_main(tmp_path):
    repo = _repo_behind_origin(tmp_path)
    origin_sha = _git(repo, "rev-parse", "origin/main").stdout.strip()
    assert _git(repo, "rev-parse", "main").stdout.strip() != origin_sha  # starts behind

    BranchManager(repo)._ff_sync_default_branch("main")

    # pure fast-forward: local main now IS the origin commit (no merge commit)
    assert _git(repo, "rev-parse", "main").stdout.strip() == origin_sha
