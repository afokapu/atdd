# URN: test:govern-lifecycle:keep-local-main-current-branch-from-origin:E010-UNIT-003-ff-default-branch-dirty-tree-skipped
# Acceptance: acc:govern-lifecycle:E010-UNIT-003-ff-default-branch-dirty-tree-skipped
# WMBT: wmbt:govern-lifecycle:E010
# Phase: RED
# Layer: backend.unit
# Assertion: behavioral

"""E010-UNIT-003 — fast_forward_default_branch skips the ff and prints a
notice when the default-branch worktree has modified tracked files.

Phase RED: fails because fast_forward_default_branch does not exist yet.
Phase GREEN: function prints notice and returns without calling merge when
             git diff --quiet HEAD exits non-zero.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.coach]


def _proc(returncode: int = 0, stdout: str = "", stderr: str = ""):
    p = MagicMock()
    p.returncode = returncode
    p.stdout = stdout
    p.stderr = stderr
    return p


def _dirty_factory(recorded: list, default_worktree_path: str = "/repos/project/main"):
    """subprocess.run side_effect simulating a dirty default-branch worktree."""

    def side_effect(cmd, **kwargs):
        recorded.append(list(cmd))

        if cmd[:2] == ["git", "fetch"]:
            return _proc(0)

        if cmd[:3] == ["git", "worktree", "list"]:
            porcelain = (
                f"worktree {default_worktree_path}\n"
                f"HEAD abc123\n"
                f"branch refs/heads/main\n\n"
            )
            return _proc(0, porcelain)

        # dirty tree — exit 1
        if cmd[:4] == ["git", "diff", "--quiet", "HEAD"]:
            return _proc(1)

        return _proc(0)

    return side_effect


def test_merge_not_called_when_dirty(tmp_path, capsys):
    """git merge --ff-only must NOT run when the default-branch worktree is dirty."""
    from atdd.coach.utils.ff_default_branch import fast_forward_default_branch

    recorded: list = []

    with patch(
        "atdd.coach.utils.ff_default_branch.subprocess.run",
        side_effect=_dirty_factory(recorded, default_worktree_path=str(tmp_path / "main")),
    ):
        fast_forward_default_branch(tmp_path, "main")

    merge_calls = [c for c in recorded if c[:3] == ["git", "merge", "--ff-only"]]
    assert not merge_calls, (
        f"Expected NO git merge --ff-only on dirty tree, but got: {merge_calls}"
    )


def test_notice_printed_when_dirty(tmp_path, capsys):
    """A human-readable notice must be printed when the ff is skipped."""
    from atdd.coach.utils.ff_default_branch import fast_forward_default_branch

    recorded: list = []

    with patch(
        "atdd.coach.utils.ff_default_branch.subprocess.run",
        side_effect=_dirty_factory(recorded, default_worktree_path=str(tmp_path / "main")),
    ):
        fast_forward_default_branch(tmp_path, "main")

    out = capsys.readouterr().out
    notice_keywords = {"skip", "modified", "dirty", "uncommitted"}
    lower_out = out.lower()
    assert any(kw in lower_out for kw in notice_keywords), (
        f"Expected a skip/modified/dirty notice in stdout, got: {out!r}"
    )


def test_function_returns_without_error_when_dirty(tmp_path):
    """fast_forward_default_branch must not raise when the tree is dirty."""
    from atdd.coach.utils.ff_default_branch import fast_forward_default_branch

    recorded: list = []

    with patch(
        "atdd.coach.utils.ff_default_branch.subprocess.run",
        side_effect=_dirty_factory(recorded, default_worktree_path=str(tmp_path / "main")),
    ):
        # Must not raise
        fast_forward_default_branch(tmp_path, "main")


def test_untracked_files_alone_do_not_block(tmp_path, capsys):
    """Untracked files (exit 0 from git diff --quiet HEAD) must not block the ff."""
    from atdd.coach.utils.ff_default_branch import fast_forward_default_branch

    recorded: list = []

    def side_effect(cmd, **kwargs):
        recorded.append(list(cmd))
        if cmd[:3] == ["git", "worktree", "list"]:
            return _proc(
                0,
                f"worktree {tmp_path / 'main'}\nHEAD abc\nbranch refs/heads/main\n\n",
            )
        # git diff --quiet HEAD: exit 0 = only untracked, no modifications
        if cmd[:4] == ["git", "diff", "--quiet", "HEAD"]:
            return _proc(0)
        return _proc(0)

    with patch(
        "atdd.coach.utils.ff_default_branch.subprocess.run",
        side_effect=side_effect,
    ):
        fast_forward_default_branch(tmp_path, "main")

    merge_calls = [c for c in recorded if c[:3] == ["git", "merge", "--ff-only"]]
    assert merge_calls, "Expected ff merge to proceed when only untracked files exist"
