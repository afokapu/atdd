# URN: test:dispatch-ux-defaults-and-primer:coach-dispatch-worktree-lifecycle:E003-UNIT-003-actionable-error-when-no-worktree-found
# Acceptance: acc:dispatch-ux-defaults-and-primer:E003-UNIT-003-actionable-error-when-no-worktree-found
# WMBT: wmbt:dispatch-ux-defaults-and-primer:E003
# Phase: RED
# Layer: domain
# Runtime: python
"""E003-UNIT-003 — find_worktree_root raises NoWorktreeFound with sibling-listing error message.

RED: NoWorktreeFound exception does not exist and find_worktree_root does not
exist. Operators who run atdd coach from a project-parent directory containing
feat-slug sibling directories get a raw git error with no actionable hint.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def test_raises_no_worktree_found_with_sibling_hint(tmp_path):
    """find_worktree_root raises NoWorktreeFound listing sibling worktree directories."""
    from atdd.coach.utils import repo

    fn = getattr(repo, "find_worktree_root", None)
    assert fn is not None, (
        "repo.find_worktree_root is not implemented — "
        "actionable NoWorktreeFound error is missing (RED)"
    )

    NoWorktreeFound = getattr(repo, "NoWorktreeFound", None)
    assert NoWorktreeFound is not None, (
        "repo.NoWorktreeFound exception is not defined — "
        "the actionable error type is missing (RED)"
    )

    # Build a flat project-parent with feat-slug siblings but no .git anywhere.
    parent = tmp_path / "my-project"
    parent.mkdir()
    (parent / "feat-slug-a").mkdir()
    (parent / "feat-slug-b").mkdir()

    with pytest.raises(NoWorktreeFound) as exc_info:
        fn(start_path=parent)

    msg = str(exc_info.value)
    assert "feat-slug-a" in msg or "feat-slug-b" in msg, (
        f"error message must list sibling directories; got: {msg!r}"
    )
    assert "--repo" in msg or "cd" in msg, (
        f"error message must suggest --repo or cd recovery; got: {msg!r}"
    )
