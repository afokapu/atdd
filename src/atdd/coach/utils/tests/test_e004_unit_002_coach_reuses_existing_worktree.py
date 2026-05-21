# URN: test:dispatch-ux-defaults-and-primer:coach-dispatch-worktree-lifecycle:E004-UNIT-002-coach-reuses-existing-worktree
# Acceptance: acc:dispatch-ux-defaults-and-primer:E004-UNIT-002-coach-reuses-existing-worktree
# WMBT: wmbt:dispatch-ux-defaults-and-primer:E004
# Phase: RED
# Layer: application
# Runtime: python
"""E004-UNIT-002 — coach worktree-setup skips 'git worktree add' when worktree exists.

RED: the coach worktree-setup path does not call find_existing_worktree_for_branch
and unconditionally runs 'git worktree add', causing a fatal error when the
worktree already exists on disk.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, call

import pytest

pytestmark = [pytest.mark.platform]


def test_worktree_add_not_called_when_existing_worktree_found(tmp_path):
    """The coach worktree-setup skips 'git worktree add' when reusing an existing worktree."""
    from atdd.coach.utils import repo

    setup_fn = getattr(repo, "ensure_issue_worktree", None)
    assert setup_fn is not None, (
        "repo.ensure_issue_worktree is not implemented — "
        "worktree-reuse guard is missing (RED)"
    )

    existing_wt = tmp_path / "feat-slug"
    existing_wt.mkdir()
    git_add_calls: list[list[str]] = []

    def fake_git_worktree_add(*args, **kwargs):
        git_add_calls.append(list(args))

    with (
        patch.object(repo, "find_existing_worktree_for_branch", return_value=existing_wt),
        patch("subprocess.run", fake_git_worktree_add),
    ):
        result = setup_fn(branch="feat/slug", repo_root=tmp_path, target_path=existing_wt)

    assert not any(
        "worktree" in str(c) and "add" in str(c) for c in git_add_calls
    ), (
        f"'git worktree add' must NOT be called when a worktree already exists; "
        f"calls recorded: {git_add_calls}"
    )

    assert result == existing_wt, (
        f"ensure_issue_worktree must return the existing worktree path; got {result!r}"
    )


def test_reuse_log_emitted_when_worktree_reused(tmp_path, capsys):
    """A 'Reusing existing worktree' message is emitted when a worktree is reused."""
    from atdd.coach.utils import repo

    setup_fn = getattr(repo, "ensure_issue_worktree", None)
    assert setup_fn is not None, (
        "repo.ensure_issue_worktree is not implemented (RED)"
    )

    existing_wt = tmp_path / "feat-slug"
    existing_wt.mkdir()

    with (
        patch.object(repo, "find_existing_worktree_for_branch", return_value=existing_wt),
        patch("subprocess.run"),
    ):
        setup_fn(branch="feat/slug", repo_root=tmp_path, target_path=existing_wt)

    out = capsys.readouterr()
    combined = out.out + out.err
    assert "Reusing existing worktree" in combined or "reusing" in combined.lower(), (
        f"reuse log message not emitted; captured output: {combined!r}"
    )
