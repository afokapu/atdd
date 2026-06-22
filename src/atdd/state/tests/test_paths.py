# URN: test:state-store:control-root-resolver:layout-modes
# Issue: #1177 (#1168 Phase 1)
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""#1177 — ATDD Control Root resolver + layout guard (#1168 Phase 1).

Covers the four resolver modes prescribed in #1168 (single-repo,
sibling-worktree, child-worktree-prefers-parent, ambiguous-fails-loud), the
layout-check rejection of a per-worktree State Store, and the doctor output.

The resolver detects Git worktree roots by the presence of a ``.git`` entry, so
these tests are hermetic — they build directory trees with empty ``.git`` /
``.atdd`` markers and never invoke git.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.state import cli as state_cli
from atdd.state.paths import (
    STATE_STORE_RELATIVE,
    AmbiguousControlRootError,
    ControlRootNotFoundError,
    LayoutMode,
    check_layout,
    resolve_control_root,
)


def _mk_worktree(path: Path) -> Path:
    """Create a directory that looks like a Git worktree root."""
    path.mkdir(parents=True, exist_ok=True)
    (path / ".git").mkdir(exist_ok=True)
    return path


def _mk_atdd(path: Path) -> Path:
    (path / ".atdd").mkdir(parents=True, exist_ok=True)
    return path


def _mk_state_store(control_root: Path) -> Path:
    store = control_root / STATE_STORE_RELATIVE
    store.parent.mkdir(parents=True, exist_ok=True)
    store.touch()
    return store


# --------------------------------------------------------------------------- #
# Resolver modes (#1168 "Control Root Resolver Rules")
# --------------------------------------------------------------------------- #
def test_state_resolver_single_repo_mode(tmp_path):
    repo = _mk_atdd(_mk_worktree(tmp_path / "repo"))

    res = resolve_control_root(repo, env={})

    assert res.layout_mode is LayoutMode.SINGLE_REPO
    assert res.control_root == repo
    assert res.git_worktree_root == repo
    assert res.state_store_path == repo / ".atdd" / "state" / "state.sqlite"


def test_state_resolver_sibling_worktree_mode(tmp_path):
    project = _mk_atdd(tmp_path / "project")        # Control Root (parent .atdd/)
    main = _mk_worktree(project / "main")           # child Git worktree, no .atdd/

    res = resolve_control_root(main, env={})

    assert res.layout_mode is LayoutMode.SIBLING_WORKTREE
    assert res.control_root == project
    assert res.git_worktree_root == main
    assert res.state_store_path == project / ".atdd" / "state" / "state.sqlite"


def test_state_resolver_prefers_parent_control_root_from_child_worktree(tmp_path):
    project = _mk_atdd(tmp_path / "project")
    worktree1 = _mk_worktree(project / "worktree1")
    deep = worktree1 / "src" / "pkg"
    deep.mkdir(parents=True)

    res = resolve_control_root(deep, env={})         # start deep inside the child worktree

    assert res.layout_mode is LayoutMode.SIBLING_WORKTREE
    assert res.control_root == project               # prefers the parent Control Root
    assert res.git_worktree_root == worktree1


def test_state_resolver_fails_on_parent_and_child_atdd(tmp_path):
    project = _mk_atdd(tmp_path / "project")
    main = _mk_atdd(_mk_worktree(project / "main"))   # BOTH parent and child have .atdd/

    with pytest.raises(AmbiguousControlRootError) as exc:
        resolve_control_root(main, env={})

    assert (project / ".atdd") == exc.value.parent_atdd
    assert (main / ".atdd") == exc.value.child_atdd


def test_state_resolver_env_override_wins(tmp_path):
    repo = _mk_atdd(_mk_worktree(tmp_path / "repo"))
    elsewhere = _mk_atdd(tmp_path / "elsewhere")

    res = resolve_control_root(repo, env={"ATDD_CONTROL_ROOT": str(elsewhere)})

    assert res.control_root == elsewhere


def test_state_resolver_raises_when_no_atdd(tmp_path):
    bare = _mk_worktree(tmp_path / "bare")           # git worktree but no .atdd anywhere

    with pytest.raises(ControlRootNotFoundError):
        resolve_control_root(bare, env={})


# --------------------------------------------------------------------------- #
# Layout guard (#1168 `atdd state layout --check`)
# --------------------------------------------------------------------------- #
def test_state_layout_check_rejects_per_worktree_state_store(tmp_path):
    project = _mk_atdd(tmp_path / "project")
    _mk_worktree(project / "main")
    rogue = _mk_worktree(project / "worktree1")
    _mk_state_store(rogue)                            # forbidden independent store

    violations = check_layout(project)

    assert violations, "a per-worktree State Store must be rejected"
    assert any("Per-worktree State Store" in v for v in violations)


def test_state_layout_check_passes_for_single_store(tmp_path):
    project = _mk_atdd(tmp_path / "project")
    _mk_worktree(project / "main")
    _mk_worktree(project / "worktree1")
    _mk_state_store(project)                          # the one legal store, at the Control Root

    assert check_layout(project) == []


# --------------------------------------------------------------------------- #
# Doctor command (#1168 `atdd state doctor`)
# --------------------------------------------------------------------------- #
def test_state_doctor_prints_control_root_and_worktree_root(tmp_path, capsys):
    project = _mk_atdd(tmp_path / "project")
    main = _mk_worktree(project / "main")

    rc = state_cli.run(["doctor", "--root", str(main)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "Control Root:" in out and str(project) in out
    assert "Git Worktree Root:" in out and str(main) in out
    assert "sibling-worktree" in out


def test_state_layout_check_cli_returns_nonzero_on_violation(tmp_path, capsys):
    project = _mk_atdd(tmp_path / "project")
    rogue = _mk_worktree(project / "worktree1")
    _mk_state_store(rogue)

    # Resolve from the Control Root: a rogue child store is a *layout* violation
    # (rc=1). Starting inside worktree1 would instead trip ambiguous-root (rc=2),
    # since the rogue store gives worktree1 its own .atdd/ beside the parent's.
    rc = state_cli.run(["layout", "--check", "--root", str(project)])
    out = capsys.readouterr().out

    assert rc == 1
    assert "Per-worktree State Store" in out
