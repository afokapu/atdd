# URN: test:dispatch-ux-defaults-and-primer:coach-dispatch-worktree-lifecycle:E003-UNIT-001-find-worktree-root-walks-up
# Acceptance: acc:dispatch-ux-defaults-and-primer:E003-UNIT-001-find-worktree-root-walks-up
# WMBT: wmbt:dispatch-ux-defaults-and-primer:E003
# Phase: RED
# Layer: domain
# Runtime: python
"""E003-UNIT-001 — find_worktree_root walks up the directory tree to find the nearest .git.

RED: find_worktree_root does not exist in src/atdd/coach/utils/repo.py yet.
Invoking atdd coach from a subdirectory of a worktree crashes with
'not a git repository' because the current implementation requires the caller
to be in the worktree root.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _make_git_worktree(root: Path, name: str) -> Path:
    """Create a minimal worktree with a real .git directory."""
    wt = root / name
    (wt / ".git").mkdir(parents=True)
    return wt


def test_find_worktree_root_walks_up_from_grandchild(tmp_path):
    """find_worktree_root returns the worktree root when called from a sub-directory."""
    from atdd.coach.utils import repo

    fn = getattr(repo, "find_worktree_root", None)
    assert fn is not None, (
        "repo.find_worktree_root is not implemented — "
        "walk-up repo detection is missing (RED)"
    )

    worktree = _make_git_worktree(tmp_path, "feat-my-branch")
    grandchild = worktree / "src" / "deep"
    grandchild.mkdir(parents=True)

    result = fn(start_path=grandchild)
    assert result == worktree, (
        f"expected worktree root {worktree}, got {result!r}"
    )


def test_find_worktree_root_returns_self_when_at_root(tmp_path):
    """find_worktree_root returns the path itself when called from the worktree root."""
    from atdd.coach.utils import repo

    fn = getattr(repo, "find_worktree_root", None)
    assert fn is not None, "repo.find_worktree_root is not implemented (RED)"

    worktree = _make_git_worktree(tmp_path, "feat-slug")
    result = fn(start_path=worktree)
    assert result == worktree, (
        f"expected {worktree} when starting at the root, got {result!r}"
    )


def test_find_worktree_root_raises_when_no_git_found(tmp_path):
    """find_worktree_root raises an exception when no .git is found up to filesystem root."""
    from atdd.coach.utils import repo

    fn = getattr(repo, "find_worktree_root", None)
    assert fn is not None, "repo.find_worktree_root is not implemented (RED)"

    no_git = tmp_path / "parent" / "child"
    no_git.mkdir(parents=True)

    with pytest.raises((FileNotFoundError, Exception)) as exc_info:
        fn(start_path=no_git)

    assert exc_info.value is not None, (
        "find_worktree_root must raise when no .git is found (RED)"
    )
