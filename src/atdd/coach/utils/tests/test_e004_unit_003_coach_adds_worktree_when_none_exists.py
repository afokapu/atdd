# URN: test:dispatch-ux-defaults-and-primer:coach-dispatch-worktree-lifecycle:E004-UNIT-003-coach-adds-worktree-when-none-exists
# Acceptance: acc:dispatch-ux-defaults-and-primer:E004-UNIT-003-coach-adds-worktree-when-none-exists
# WMBT: wmbt:dispatch-ux-defaults-and-primer:E004
# Phase: RED
# Layer: application
# Runtime: python
"""E004-UNIT-003 — coach calls 'git worktree add' normally when no existing worktree found.

RED: ensure_issue_worktree does not exist. When find_existing_worktree_for_branch
returns None (no prior worktree), the setup path must still create a new one
via 'git worktree add' — the happy path must work alongside the reuse guard.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

pytestmark = [pytest.mark.platform]


def test_git_worktree_add_called_when_no_existing_worktree(tmp_path):
    """ensure_issue_worktree calls 'git worktree add' when no existing worktree is found."""
    from atdd.coach.utils import repo

    setup_fn = getattr(repo, "ensure_issue_worktree", None)
    assert setup_fn is not None, (
        "repo.ensure_issue_worktree is not implemented — "
        "new-worktree creation path is missing (RED)"
    )

    target = tmp_path / "feat-new-feature"
    subprocess_calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        subprocess_calls.append(list(cmd))
        target.mkdir(exist_ok=True)
        return MagicMock(returncode=0, stdout="", stderr="")

    with (
        patch.object(repo, "find_existing_worktree_for_branch", return_value=None),
        patch("subprocess.run", fake_run),
    ):
        setup_fn(branch="feat/new-feature", repo_root=tmp_path, target_path=target)

    assert any(
        "worktree" in " ".join(c) and "add" in " ".join(c)
        for c in subprocess_calls
    ), (
        f"'git worktree add' must be called when no existing worktree is found; "
        f"calls recorded: {subprocess_calls}"
    )


def test_no_reuse_log_emitted_when_creating_new_worktree(tmp_path, capsys):
    """No 'Reusing existing worktree' log is emitted when creating a new worktree."""
    from atdd.coach.utils import repo

    setup_fn = getattr(repo, "ensure_issue_worktree", None)
    assert setup_fn is not None, "repo.ensure_issue_worktree is not implemented (RED)"

    target = tmp_path / "feat-new-feature"

    def fake_run(cmd, **kwargs):
        target.mkdir(exist_ok=True)
        return MagicMock(returncode=0, stdout="", stderr="")

    with (
        patch.object(repo, "find_existing_worktree_for_branch", return_value=None),
        patch("subprocess.run", fake_run),
    ):
        setup_fn(branch="feat/new-feature", repo_root=tmp_path, target_path=target)

    out = capsys.readouterr()
    combined = out.out + out.err
    assert "Reusing existing worktree" not in combined, (
        f"reuse log must NOT appear when creating a new worktree; got: {combined!r}"
    )
