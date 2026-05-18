# URN: test:govern-lifecycle:keep-local-main-current-branch-from-origin:E010-UNIT-002-ff-default-branch-clean-tree
# Acceptance: acc:govern-lifecycle:E010-UNIT-002-ff-default-branch-clean-tree
# WMBT: wmbt:govern-lifecycle:E010
# Phase: RED
# Layer: backend.unit
# Assertion: behavioral

"""E010-UNIT-002 — fast_forward_default_branch runs git merge --ff-only
origin/<default_branch> in the default-branch worktree when its tracked tree
is clean.

Phase RED: fails because fast_forward_default_branch does not exist yet.
Phase GREEN: function exists, does targeted fetch, checks dirty state, runs
             git merge --ff-only when clean.
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


def _run_factory(
    recorded: list,
    default_branch: str = "main",
    default_worktree_path: str = "/repos/project/main",
    dirty: bool = False,
):
    """subprocess.run side_effect for the ff_default_branch utility."""

    def side_effect(cmd, **kwargs):
        recorded.append(list(cmd))

        # git fetch origin <default_branch>
        if cmd[:2] == ["git", "fetch"]:
            return _proc(0)

        # git worktree list --porcelain — returns the default-branch worktree
        if cmd[:3] == ["git", "worktree", "list"]:
            porcelain = (
                f"worktree {default_worktree_path}\n"
                f"HEAD abc123\n"
                f"branch refs/heads/{default_branch}\n\n"
            )
            return _proc(0, porcelain)

        # git diff --quiet HEAD — 0 = clean, 1 = dirty
        if cmd[:4] == ["git", "diff", "--quiet", "HEAD"]:
            return _proc(1 if dirty else 0)

        # git merge --ff-only — success
        if cmd[:3] == ["git", "merge", "--ff-only"]:
            return _proc(0)

        return _proc(0)

    return side_effect


def test_ff_runs_when_clean(tmp_path):
    """fast_forward_default_branch calls git merge --ff-only when tree is clean."""
    from atdd.coach.utils.ff_default_branch import fast_forward_default_branch

    recorded: list = []

    with patch(
        "atdd.coach.utils.ff_default_branch.subprocess.run",
        side_effect=_run_factory(recorded, default_worktree_path=str(tmp_path / "main")),
    ):
        fast_forward_default_branch(tmp_path, "main")

    merge_calls = [c for c in recorded if c[:3] == ["git", "merge", "--ff-only"]]
    assert merge_calls, "Expected git merge --ff-only to be called on clean tree"

    assert "origin/main" in merge_calls[0], (
        f"Expected 'origin/main' in merge command, got: {merge_calls[0]}"
    )


def test_fetch_before_merge(tmp_path):
    """git fetch origin <default_branch> must precede git merge --ff-only."""
    from atdd.coach.utils.ff_default_branch import fast_forward_default_branch

    recorded: list = []

    with patch(
        "atdd.coach.utils.ff_default_branch.subprocess.run",
        side_effect=_run_factory(recorded, default_worktree_path=str(tmp_path / "main")),
    ):
        fast_forward_default_branch(tmp_path, "main")

    fetch_idx = next(
        (i for i, c in enumerate(recorded) if c[:2] == ["git", "fetch"] and "main" in c),
        None,
    )
    merge_idx = next(
        (i for i, c in enumerate(recorded) if c[:3] == ["git", "merge", "--ff-only"]),
        None,
    )
    assert fetch_idx is not None, "No git fetch call found"
    assert merge_idx is not None, "No git merge --ff-only call found"
    assert fetch_idx < merge_idx, (
        f"fetch (idx {fetch_idx}) must precede merge (idx {merge_idx})"
    )


def test_no_rebase_or_merge_commit(tmp_path):
    """fast_forward_default_branch must never run git rebase or non-ff merge."""
    from atdd.coach.utils.ff_default_branch import fast_forward_default_branch

    recorded: list = []

    with patch(
        "atdd.coach.utils.ff_default_branch.subprocess.run",
        side_effect=_run_factory(recorded, default_worktree_path=str(tmp_path / "main")),
    ):
        fast_forward_default_branch(tmp_path, "main")

    rebase_calls = [c for c in recorded if "rebase" in c]
    assert not rebase_calls, f"Unexpected git rebase call: {rebase_calls}"

    unsafe_merge = [
        c for c in recorded
        if c[:2] == ["git", "merge"] and "--ff-only" not in c
    ]
    assert not unsafe_merge, f"Unexpected non-ff-only merge call: {unsafe_merge}"


def test_diff_check_runs_in_default_worktree(tmp_path):
    """git diff --quiet HEAD must run inside the default-branch worktree (cwd check)."""
    from atdd.coach.utils.ff_default_branch import fast_forward_default_branch

    default_wt = tmp_path / "main"
    default_wt.mkdir()
    recorded_cwds: list = []

    def side_effect(cmd, **kwargs):
        if cmd[:4] == ["git", "diff", "--quiet", "HEAD"]:
            recorded_cwds.append(kwargs.get("cwd"))
        if cmd[:3] == ["git", "worktree", "list"]:
            porcelain = (
                f"worktree {default_wt}\n"
                f"HEAD abc123\n"
                f"branch refs/heads/main\n\n"
            )
            p = MagicMock()
            p.returncode = 0
            p.stdout = porcelain
            p.stderr = ""
            return p
        p = MagicMock()
        p.returncode = 0
        p.stdout = ""
        p.stderr = ""
        return p

    with patch(
        "atdd.coach.utils.ff_default_branch.subprocess.run",
        side_effect=side_effect,
    ):
        fast_forward_default_branch(tmp_path, "main")

    assert recorded_cwds, "git diff --quiet HEAD was never called"
    assert any(
        Path(str(cwd)).resolve() == default_wt.resolve()
        for cwd in recorded_cwds
    ), f"Expected diff check cwd={default_wt}, got: {recorded_cwds}"
