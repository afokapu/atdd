# URN: test:migrate-projection-authority:migrate-store-projection:C002-UNIT-003-the-projection-path-is-inside-the-worktree
# Acceptance: acc:migrate-projection-authority:C002-UNIT-003-the-projection-path-is-inside-the-worktree
# WMBT: wmbt:migrate-projection-authority:C002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: In sibling-worktree layout every default resolver of the projection directory names one path inside the git worktree — the writer's --out, the cutover's root, and reconcile's projection_path as used by hydrate and reconcile. Refs #2024.
"""One projection directory, and it is inside git (C002-UNIT-003).

wagon: migrate-projection-authority | feature: migrate-store-projection | phase: RED
WMBT: wmbt:migrate-projection-authority:C002

``PROJECTION_RELATIVE`` is a path *relative to something*, and the codebase never settled what.
The writer anchors it to the **Control Root** (``projection_cli`` -> ``resolve_control_root``);
the git readers anchor it to the **git repo** (``merge_authority``, ``gitstore``); and
``reconcile.projection_path`` anchors it to the Control Root again, for ``hydrate`` and
``reconcile``. Those were one directory in single-repo mode, so the divergence was invisible
until sibling-worktree layout made the Control Root a deliberately non-git parent.

The projection is a **committed** artifact. It cannot live at the Control Root, because in this
layout the Control Root is not a git repository at all. Refs #2024 / #1622.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from atdd.state import reconcile
from atdd.state.paths import LayoutMode, resolve_control_root
from atdd.state.projection import PROJECTION_RELATIVE

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


def test_reconcile_projection_path_resolves_inside_the_worktree(tmp_path: Path) -> None:
    """``hydrate`` (and ``reconcile``) must not read a directory git cannot see.

    RED: ``reconcile.projection_path`` returns ``<control-root>/.atdd/state/projection``, so
    ordinary reconciliation reads the non-git parent.
    """
    parent, worktree = _sibling_layout(tmp_path)

    resolved = reconcile.projection_path(parent)

    assert resolved == worktree / PROJECTION_RELATIVE, (
        f"reconcile.projection_path resolved {resolved}, which is outside the git worktree "
        f"{worktree}; hydrate and reconcile would read a directory no commit can contain"
    )


def test_every_default_resolver_names_the_same_directory(tmp_path: Path) -> None:
    """The writer's default and reconcile's default must not disagree.

    RED: they disagree by construction — one is anchored at the Control Root and the git
    readers are anchored at the repo.
    """
    from atdd.state import projection_cli

    parent, worktree = _sibling_layout(tmp_path)

    writer_default = projection_cli._projection_dir(  # noqa: SLF001 — the default under test
        type("Args", (), {"root": str(worktree), "out": None, "from_dir": None})(),
    )
    reader_default = reconcile.projection_path(parent)
    git_reader_default = worktree / PROJECTION_RELATIVE

    assert writer_default == git_reader_default, (
        f"`atdd state project` defaults to {writer_default}, but every git reader looks in "
        f"{git_reader_default}"
    )
    assert reader_default == git_reader_default, (
        f"reconcile resolves {reader_default}, but every git reader looks in {git_reader_default}"
    )
