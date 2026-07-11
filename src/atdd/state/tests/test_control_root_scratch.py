# URN: test:state-store:control-root-resolver:scratch-vs-real
# Issue: #1179 (#1168 follow-up; refines #1177)
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""#1179 — distinguish a real Control Root from a scratch ``.atdd/``.

A ``.atdd/`` is a Control Root only if it carries an initialized-root signal
(``config.yaml`` / ``state/`` / an explicit marker; ``manifest.yaml`` was retired
as a marker in #1270 Slice G). A
scratch-only ``.atdd/`` (just ``cache/`` / ``runtime/`` / ``diagnostics/``, as
tools leave at a flat-worktree parent) must be ignored — it must NOT shadow a
real worktree Control Root nor trigger a false ambiguity. This is the bug the
#1177 resolver exposed on the real flat-sibling-worktree dev environment.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from atdd.state import cli as state_cli
from atdd.state.paths import (
    AmbiguousControlRootError,
    ControlRootNotFoundError,
    LayoutMode,
    is_control_root,
    is_scratch_atdd,
    resolve_control_root,
)

_SRC = Path(__file__).resolve().parents[3]


def _mk_worktree(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / ".git").mkdir(exist_ok=True)
    return path


def _scratch_atdd(path: Path) -> Path:
    """A .atdd/ with only tool scratch — NOT a Control Root."""
    for d in ("cache", "runtime", "diagnostics"):
        (path / ".atdd" / d).mkdir(parents=True, exist_ok=True)
    return path


def _real_atdd(path: Path, marker: str = "config.yaml") -> Path:
    """A .atdd/ carrying an initialized-root signal."""
    (path / ".atdd").mkdir(parents=True, exist_ok=True)
    if marker == "state":
        (path / ".atdd" / "state").mkdir(exist_ok=True)
    else:
        (path / ".atdd" / marker).write_text("x\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# Predicates
# --------------------------------------------------------------------------- #
def test_scratch_only_atdd_is_not_a_control_root(tmp_path):
    d = _scratch_atdd(tmp_path / "parent")
    assert is_control_root(d) is False
    assert is_scratch_atdd(d) is True


@pytest.mark.parametrize("marker", ["config.yaml", "state", "control-root.yaml"])
def test_control_root_recognized_by_any_marker(tmp_path, marker):
    d = _real_atdd(tmp_path / f"root-{marker}", marker=marker)
    assert is_control_root(d) is True
    assert is_scratch_atdd(d) is False


def test_absent_atdd_is_neither(tmp_path):
    d = tmp_path / "empty"
    d.mkdir()
    assert is_control_root(d) is False
    assert is_scratch_atdd(d) is False


# --------------------------------------------------------------------------- #
# Resolver behavior (the #1177-exposed bug + preserved cases)
# --------------------------------------------------------------------------- #
def test_resolver_ignores_scratch_parent_and_picks_worktree(tmp_path):
    """The real dev-env case: scratch parent .atdd/ beside a real worktree .atdd/.

    Before #1179 this raised AmbiguousControlRootError; now the scratch parent is
    ignored and the worktree resolves cleanly as single-repo.
    """
    project = _scratch_atdd(tmp_path / "project")        # parent: scratch only
    main = _real_atdd(_mk_worktree(project / "main"))     # child worktree: real .atdd/

    res = resolve_control_root(main, env={})

    assert res.layout_mode is LayoutMode.SINGLE_REPO
    assert res.control_root == main
    assert res.git_worktree_root == main


def test_resolver_still_sibling_when_parent_is_real_control_root(tmp_path):
    project = _real_atdd(tmp_path / "project")            # parent: real Control Root
    main = _mk_worktree(project / "main")                 # child worktree: no .atdd/

    res = resolve_control_root(main, env={})

    assert res.layout_mode is LayoutMode.SIBLING_WORKTREE
    assert res.control_root == project


def test_resolver_ambiguous_only_when_both_are_real(tmp_path):
    project = _real_atdd(tmp_path / "project")
    main = _real_atdd(_mk_worktree(project / "main"))     # BOTH real → still ambiguous

    with pytest.raises(AmbiguousControlRootError):
        resolve_control_root(main, env={})


def test_resolver_not_found_when_only_scratch_anywhere(tmp_path):
    project = _scratch_atdd(tmp_path / "project")
    main = _scratch_atdd(_mk_worktree(project / "main"))  # scratch both → no real root

    with pytest.raises(ControlRootNotFoundError):
        resolve_control_root(main, env={})


# --------------------------------------------------------------------------- #
# Doctor diagnostic + live smoke
# --------------------------------------------------------------------------- #
def test_doctor_reports_ignored_scratch_parent(tmp_path, capsys):
    project = _scratch_atdd(tmp_path / "project")
    main = _real_atdd(_mk_worktree(project / "main"))

    rc = state_cli.run(["doctor", "--root", str(main)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "single-repo" in out
    assert "ignored scratch .atdd" in out


def test_doctor_ignores_scratch_parent_live(tmp_path):
    project = _scratch_atdd(tmp_path / "project")
    main = _real_atdd(_mk_worktree(project / "main"))
    env = {"PYTHONPATH": str(_SRC), "PATH": __import__("os").environ.get("PATH", ""),
           "HOME": str(project), "CI": "true"}
    r = subprocess.run([sys.executable, "-m", "atdd", "state", "doctor", "--root", str(main)],
                       cwd=str(main), env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert "single-repo" in (r.stdout + r.stderr)
