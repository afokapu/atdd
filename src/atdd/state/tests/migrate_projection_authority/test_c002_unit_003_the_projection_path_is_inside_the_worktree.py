# URN: test:migrate-projection-authority:migrate-store-projection:C002-UNIT-003-the-projection-path-is-inside-the-worktree
# Acceptance: acc:migrate-projection-authority:C002-UNIT-003-the-projection-path-is-inside-the-worktree
# WMBT: wmbt:migrate-projection-authority:C002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: The writer's default projection directory must be inside the git worktree in BOTH layouts. reconcile's projection_path needs no change: assert_reconcilable refuses sibling layout outright, so its Control-Root anchoring is unreachable there and already correct in single-repo. Refs #2024.
"""One projection directory, and it is inside git (C002-UNIT-003).

wagon: migrate-projection-authority | feature: migrate-store-projection | phase: RED
WMBT: wmbt:migrate-projection-authority:C002

``PROJECTION_RELATIVE`` is a path *relative to something*, and the codebase never settled what.
The writer anchors it to the **Control Root** (``projection_cli`` -> ``resolve_control_root``)
while the git readers anchor it to the **git repo** (``merge_authority``, ``gitstore``). Those
were one directory in single-repo mode, so the divergence stayed invisible until
sibling-worktree layout made the Control Root a deliberately non-git parent. The projection is
a **committed** artifact; it cannot live there.

``reconcile.projection_path`` anchors at the Control Root too, and an earlier revision of this
issue called that a second instance of the same defect. It is not, and this module pins why so
the claim is not re-derived: ``assert_reconcilable`` (#1580) refuses a Control Root that is not
itself the git checkout, and it gates **both** call sites — ``hydrate`` at :442 before :444,
``reconcile`` at :811 before :813. In sibling layout reconciliation therefore *refuses* rather
than reading the parent path, and in single-repo layout the Control Root **is** the worktree, so
the path already agrees with the git readers. Changing it would be a no-op in the reachable
cases. Refs #2024 / #1622 / #1580.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atdd.state import reconcile
from atdd.state.paths import LayoutMode, resolve_control_root
from atdd.state.projection import PROJECTION_RELATIVE

from atdd.state.tests._fixtures import make_checkout
from ._helpers import control_root


def _sibling_layout(tmp_path: Path) -> tuple[Path, Path]:
    """A Control Root parent that is NOT a git repo, with a git worktree child inside it."""
    parent = control_root(tmp_path / "project")
    (parent / ".atdd" / "state").mkdir(parents=True, exist_ok=True)
    worktree = parent / "main"
    worktree.mkdir()
    subprocess.run(["git", "init", "--quiet", "--initial-branch=main", str(worktree)],
                   check=True, capture_output=True, timeout=60)
    return parent, worktree


def test_the_control_root_is_not_a_git_repository(tmp_path: Path) -> None:
    """The premise: in this layout the Control Root cannot contain a commit."""
    parent, worktree = _sibling_layout(tmp_path)
    resolution = resolve_control_root(worktree)

    assert resolution.layout_mode is LayoutMode.SIBLING_WORKTREE
    assert resolution.control_root == parent
    assert resolution.git_worktree_root == worktree

    inside_git = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=str(parent), capture_output=True, text=True, timeout=60,
    )
    assert inside_git.returncode != 0, (
        "the Control Root is a git repository in this fixture, so the divergence this "
        "acceptance is about cannot be observed"
    )


def test_the_writer_writes_where_no_commit_can_reach(tmp_path: Path) -> None:
    """The defect: ``atdd state project``'s default output is outside git in this layout.

    RED: it anchors at the Control Root, which is not a git repository, so the projection it
    writes can never be committed and the git readers can never see it.
    """
    from atdd.state import projection_cli

    _parent, worktree = _sibling_layout(tmp_path)

    # A private helper on purpose: the DEFAULT is what is under test, and it is resolved here.
    writer_default = projection_cli._projection_dir(
        type("Args", (), {"root": str(worktree), "out": None, "from_dir": None})(),
    )

    assert writer_default.is_relative_to(worktree), (
        f"`atdd state project` defaults to {writer_default}, which is outside the git worktree "
        f"{worktree}; no commit can contain it, so the projection can never become shared state"
    )
    assert writer_default == worktree / PROJECTION_RELATIVE, (
        f"the writer's default {writer_default} is not the directory every git reader looks in, "
        f"{worktree / PROJECTION_RELATIVE}"
    )


def test_reconcile_refuses_sibling_layout_rather_than_reading_the_parent_path(
    tmp_path: Path,
) -> None:
    """Why ``reconcile.projection_path`` is NOT a second instance of the defect.

    A guard, not a RED driver. ``assert_reconcilable`` gates every call site, so in sibling
    layout reconciliation refuses outright and the Control-Root-anchored path is never read.
    If that guard is ever relaxed, this test fails and the path question becomes live — which
    is exactly when someone needs to be told.
    """
    parent, _worktree = _sibling_layout(tmp_path)

    with pytest.raises(reconcile.SharedStoreReconcileRefused):
        reconcile.assert_reconcilable(parent)


def test_single_repo_layout_already_agrees(tmp_path: Path) -> None:
    """In the layout that ships to consumers, every default resolver already names one path.

    A guard: the fix must not move the case that is already correct.
    """
    repo = make_checkout(tmp_path / "solo")
    (repo / ".atdd" / "state").mkdir(parents=True, exist_ok=True)

    resolution = resolve_control_root(repo)
    assert resolution.layout_mode is LayoutMode.SINGLE_REPO
    assert reconcile.projection_path(repo) == repo / PROJECTION_RELATIVE
