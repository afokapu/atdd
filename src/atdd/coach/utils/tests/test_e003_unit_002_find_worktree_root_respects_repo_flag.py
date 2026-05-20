# URN: test:dispatch-ux-defaults-and-primer:coach-dispatch-worktree-lifecycle:E003-UNIT-002-find-worktree-root-respects-repo-flag
# Acceptance: acc:dispatch-ux-defaults-and-primer:E003-UNIT-002-find-worktree-root-respects-repo-flag
# WMBT: wmbt:dispatch-ux-defaults-and-primer:E003
# Phase: RED
# Layer: application
# Runtime: python
"""E003-UNIT-002 — resolve_repo_path returns explicit_path without walking when provided.

RED: resolve_repo_path does not exist in repo.py. The --repo flag cannot be
honored because there is no resolution helper that short-circuits the
walk-up when an explicit path is given.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _make_git_dir(root: Path, name: str) -> Path:
    wt = root / name
    (wt / ".git").mkdir(parents=True)
    return wt


def test_resolve_repo_path_returns_explicit_path(tmp_path):
    """resolve_repo_path returns the explicit path when one is provided."""
    from atdd.coach.utils import repo

    fn = getattr(repo, "resolve_repo_path", None)
    assert fn is not None, (
        "repo.resolve_repo_path is not implemented — "
        "--repo flag short-circuit is missing (RED)"
    )

    explicit = _make_git_dir(tmp_path, "my-worktree")
    cwd = tmp_path / "some-other-dir"
    cwd.mkdir()

    result = fn(explicit_path=explicit, cwd=cwd)
    assert result == explicit, (
        f"explicit_path must be returned without walking; got {result!r}"
    )


def test_resolve_repo_path_falls_back_to_walk_when_no_explicit(tmp_path):
    """resolve_repo_path falls back to find_worktree_root when explicit_path is None."""
    from atdd.coach.utils import repo

    fn = getattr(repo, "resolve_repo_path", None)
    assert fn is not None, (
        "repo.resolve_repo_path is not implemented (RED)"
    )

    worktree = _make_git_dir(tmp_path, "feat-slug")
    subdir = worktree / "src"
    subdir.mkdir()

    result = fn(explicit_path=None, cwd=subdir)
    assert result == worktree, (
        f"when explicit_path is None, must walk to {worktree}; got {result!r}"
    )
