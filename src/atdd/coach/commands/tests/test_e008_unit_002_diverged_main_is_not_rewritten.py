# URN: test:drive-state-machine:consolidate-worktree-command:E008-UNIT-002-diverged-main-is-not-rewritten
# Acceptance: acc:drive-state-machine:E008-UNIT-002-diverged-main-is-not-rewritten
# WMBT: wmbt:drive-state-machine:E008
# Phase: RED
# Harness: unit
# Layer: domain
"""E008-UNIT-002 — a diverged default branch is never rewritten (loud skip).

Issue #1347. When local ``main`` has commits NOT on ``origin/main`` (diverged,
ahead>=1), ``_ff_sync_default_branch`` must skip — preserving the local commits
and never rewriting history — and say so. This is the guard that protects the
63-ahead diverged local main the issue describes.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atdd.coach.commands.branch import BranchManager

pytestmark = [pytest.mark.platform]


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True)


def _repo_diverged_from_origin(tmp_path: Path) -> Path:
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
    # origin gets B; local rewinds and makes its OWN commit C → diverged
    (repo / "f.txt").write_text("A\nB\n")
    _git(repo, "commit", "-am", "B")
    _git(repo, "push", "origin", "main")
    _git(repo, "reset", "--hard", "HEAD~1")
    (repo / "g.txt").write_text("C\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "C")
    return repo


def test_e008_unit_002_diverged_main_is_not_rewritten(tmp_path, capsys):
    repo = _repo_diverged_from_origin(tmp_path)
    local_before = _git(repo, "rev-parse", "main").stdout.strip()

    BranchManager(repo)._ff_sync_default_branch("main")

    assert _git(repo, "rev-parse", "main").stdout.strip() == local_before  # unchanged
    assert "diverged" in capsys.readouterr().out.lower()
