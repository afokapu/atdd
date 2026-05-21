# URN: test:dispatch-ux-defaults-and-primer:coach-dispatch-worktree-lifecycle:E004-UNIT-001-detect-existing-worktree
# Acceptance: acc:dispatch-ux-defaults-and-primer:E004-UNIT-001-detect-existing-worktree
# WMBT: wmbt:dispatch-ux-defaults-and-primer:E004
# Phase: RED
# Layer: integration
# Runtime: python
"""E004-UNIT-001 — find_existing_worktree_for_branch returns path when branch has a worktree.

RED: find_existing_worktree_for_branch does not exist in repo.py. The coach
unconditionally runs 'git worktree add' even when the worktree already exists,
causing 'fatal: <path> already exists' on every re-run.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.platform]

_PORCELAIN_WITH_MATCH = """\
worktree /projects/feat-slug
HEAD abc123def456
branch refs/heads/feat/slug

worktree /projects/main
HEAD 111222333444
branch refs/heads/main

"""

_PORCELAIN_NO_MATCH = """\
worktree /projects/main
HEAD 111222333444
branch refs/heads/main

"""


def test_returns_path_when_branch_exists(tmp_path):
    """find_existing_worktree_for_branch returns the Path when a worktree tracks the branch."""
    from atdd.coach.utils import repo

    fn = getattr(repo, "find_existing_worktree_for_branch", None)
    assert fn is not None, (
        "repo.find_existing_worktree_for_branch is not implemented — "
        "worktree-reuse detection is missing (RED)"
    )

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = type(
            "CP", (), {"returncode": 0, "stdout": _PORCELAIN_WITH_MATCH, "stderr": ""}
        )()
        result = fn(branch="feat/slug", repo_root=tmp_path)

    assert result == Path("/projects/feat-slug"), (
        f"expected Path('/projects/feat-slug'), got {result!r}"
    )


def test_returns_none_when_branch_not_found(tmp_path):
    """find_existing_worktree_for_branch returns None when no worktree tracks the branch."""
    from atdd.coach.utils import repo

    fn = getattr(repo, "find_existing_worktree_for_branch", None)
    assert fn is not None, (
        "repo.find_existing_worktree_for_branch is not implemented (RED)"
    )

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = type(
            "CP", (), {"returncode": 0, "stdout": _PORCELAIN_NO_MATCH, "stderr": ""}
        )()
        result = fn(branch="feat/nonexistent", repo_root=tmp_path)

    assert result is None, (
        f"expected None when no worktree matches branch, got {result!r}"
    )
