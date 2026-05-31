# URN: component:govern-lifecycle:enforcement-substrate:test_cleanup_command:backend:domain
# Runtime: python
# Purpose: `atdd cleanup` removes merged worktrees + orphan branches but never main /
#          unmerged / dirty worktrees (#928 Gap 2).
"""
Tests for ``atdd cleanup`` (issue #928 Gap 2).

Drive the pure decision (``evaluate_worktree_removable``) plus an integration
test against a throwaway git repo + linked worktree under ``tmp_path`` (never
touches the live repo).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atdd.coach.commands.cleanup import (
    Removable,
    evaluate_worktree_removable,
    find_removable,
)

pytestmark = [pytest.mark.coach]


# --- pure decision -------------------------------------------------------
def test_main_never_removed():
    ok, reason = evaluate_worktree_removable(
        branch="main", is_main=True, branch_merged=True, has_uncommitted=False)
    assert ok is False and "main" in reason


def test_merged_clean_branch_is_removable():
    ok, _ = evaluate_worktree_removable(
        branch="feat/x", is_main=False, branch_merged=True, has_uncommitted=False)
    assert ok is True


def test_unmerged_branch_kept():
    ok, reason = evaluate_worktree_removable(
        branch="feat/x", is_main=False, branch_merged=False, has_uncommitted=False)
    assert ok is False and "not merged" in reason


def test_dirty_worktree_skipped_even_if_merged():
    ok, reason = evaluate_worktree_removable(
        branch="feat/x", is_main=False, branch_merged=True, has_uncommitted=True)
    assert ok is False and "uncommitted" in reason


def test_detached_head_skipped():
    ok, _ = evaluate_worktree_removable(
        branch=None, is_main=False, branch_merged=True, has_uncommitted=False)
    assert ok is False


# --- integration against a throwaway repo --------------------------------
def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout.strip()


def _init_repo(repo: Path) -> None:
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@t.t")
    _git(repo, "config", "user.name", "t")
    (repo / "f.txt").write_text("v1\n")
    _git(repo, "add", "f.txt")
    _git(repo, "-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", "init")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")


def test_find_removable_detects_merged_worktree_not_unmerged_or_prep(tmp_path, monkeypatch):
    """Merged-PR branch → removable; unmerged, prep (0-commit), and main → kept."""
    repo = tmp_path / "main"
    _init_repo(repo)

    # Merged worktree (mocked below as having a merged PR).
    merged_wt = tmp_path / "feat-merged"
    _git(repo, "worktree", "add", "-q", str(merged_wt), "-b", "feat/merged")

    # Unmerged worktree (no PR).
    unmerged_wt = tmp_path / "feat-unmerged"
    _git(repo, "worktree", "add", "-q", str(unmerged_wt), "-b", "feat/unmerged")
    (unmerged_wt / "h.txt").write_text("y\n"); _git(unmerged_wt, "add", "h.txt")
    _git(unmerged_wt, "-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", "wip")

    # Prep worktree: 0 commits ahead (tip == main), no PR — must NOT be removed.
    prep_wt = tmp_path / "feat-prep"
    _git(repo, "worktree", "add", "-q", str(prep_wt), "-b", "feat/prep", "main")

    # Only feat/merged "has a merged PR".
    monkeypatch.setattr(
        "atdd.coach.commands.cleanup._has_merged_pr",
        lambda root, branch: branch == "feat/merged",
    )

    branches = {i.name for i in find_removable(repo) if i.kind == "worktree"}
    assert "feat/merged" in branches
    assert "feat/unmerged" not in branches
    assert "feat/prep" not in branches, "0-commit prep worktree must never be removed"
    assert "main" not in branches


def test_find_removable_skips_dirty_merged_worktree(tmp_path, monkeypatch):
    repo = tmp_path / "main"
    _init_repo(repo)
    wt = tmp_path / "feat-merged-dirty"
    _git(repo, "worktree", "add", "-q", str(wt), "-b", "feat/merged-dirty")
    (wt / "dirty.txt").write_text("uncommitted\n")  # uncommitted change

    monkeypatch.setattr(
        "atdd.coach.commands.cleanup._has_merged_pr", lambda root, branch: True)

    assert "feat/merged-dirty" not in {i.name for i in find_removable(repo) if i.kind == "worktree"}
