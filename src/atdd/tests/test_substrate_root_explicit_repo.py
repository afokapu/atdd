"""Tests for ``atdd.cli._substrate_root`` — explicit ``--repo`` vs implicit cwd (#1601).

The flat-sibling worktree layout resolves every worktree's Control Root to the
project root (``paths.resolve_control_root`` rules 1.4/1.5, #1315/#1346), and
``_substrate_root`` routed the substrate CLI's project root through that resolver.
That is correct for the *implicit* target — a bare ``atdd substrate add`` from a
worktree must not fork the shared ``.atdd/``. It was wrong for an *explicit*
``--repo PATH``: the one path the operator named was discarded, which left no way
to target a worktree's own ``.atdd/extensions/`` — the tracked, vendored location
this repo actually commits extensions to.

So: explicit wins verbatim, implicit still consolidates. The consolidation arm is
built over a *real* ``git worktree`` (as E005-SMOKE-001 does) because the redirect
is derived from ``git rev-parse --git-common-dir``; an empty ``.git`` marker under
``tmp_path`` would silently exercise the marker-based fallback instead, and a test
that passes for the wrong reason is worse than no test.
"""
from __future__ import annotations

import shutil
import subprocess
from argparse import Namespace
from pathlib import Path

import pytest

from atdd.cli import _substrate_root
from atdd.substrate import installer


def _mk_marker_worktree(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / ".git").mkdir(exist_ok=True)
    (path / ".atdd").mkdir(parents=True, exist_ok=True)
    (path / ".atdd" / "config.yaml").write_text("x\n", encoding="utf-8")
    return path


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


def _flat_sibling_project(tmp_path: Path) -> tuple[Path, Path]:
    """A genuine flat-sibling layout: ``<project>/main`` + a linked ``<project>/wt1``."""
    project = tmp_path / "project"
    main = project / "main"
    main.mkdir(parents=True)
    _git(main, "init", "-q")
    _git(main, "config", "user.email", "t@t.t")
    _git(main, "config", "user.name", "t")
    (main / ".atdd").mkdir()
    (main / ".atdd" / "config.yaml").write_text("x\n", encoding="utf-8")
    (main / "f.txt").write_text("x\n", encoding="utf-8")
    _git(main, "add", "-A")
    _git(main, "commit", "-qm", "init")
    wt1 = project / "wt1"
    _git(main, "worktree", "add", "-q", str(wt1), "-b", "wt1")
    return project, wt1


def test_explicit_repo_is_honored_verbatim(tmp_path, monkeypatch):
    """``--repo <worktree>`` targets that worktree, not the shared Control Root."""
    project = tmp_path / "project"
    _mk_marker_worktree(project / "main")
    wt = _mk_marker_worktree(project / "wt1")
    (project / ".atdd").mkdir(parents=True, exist_ok=True)
    (project / ".atdd" / "config.yaml").write_text("x\n", encoding="utf-8")
    monkeypatch.chdir(wt)

    root = _substrate_root(Namespace(repo=str(wt)))

    assert Path(root) == wt.resolve()


def test_explicit_relative_repo_is_resolved_against_cwd(tmp_path, monkeypatch):
    """A relative ``--repo`` is made absolute, still without resolver redirection."""
    project = tmp_path / "project"
    _mk_marker_worktree(project / "main")
    wt = _mk_marker_worktree(project / "wt1")
    monkeypatch.chdir(project)

    root = _substrate_root(Namespace(repo="wt1"))

    assert Path(root) == wt.resolve()


@pytest.mark.skipif(shutil.which("git") is None, reason="git required for the live worktree layout")
def test_explicit_repo_puts_the_install_home_in_that_worktree(tmp_path, monkeypatch):
    """The payoff: over a real flat-sibling layout, ``--repo <wt>`` makes the worktree's
    own vendored ``.atdd/extensions/`` reachable — which is what a re-vendor needs."""
    project, wt1 = _flat_sibling_project(tmp_path)
    monkeypatch.chdir(wt1)
    monkeypatch.delenv("ATDD_CONTROL_ROOT", raising=False)

    home = installer.install_path(
        _substrate_root(Namespace(repo=str(wt1))), "extension", "atdd.extension.demo", "0.1.0"
    )

    assert home == wt1 / ".atdd" / "extensions" / "atdd.extension.demo" / "0.1.0"


@pytest.mark.skipif(shutil.which("git") is None, reason="git required for the live worktree layout")
def test_implicit_cwd_still_consolidates_on_the_control_root(tmp_path, monkeypatch):
    """No ``--repo``: the bare command still lands on the shared project root (#1346)."""
    project, wt1 = _flat_sibling_project(tmp_path)
    monkeypatch.chdir(wt1)
    monkeypatch.delenv("ATDD_CONTROL_ROOT", raising=False)

    root = _substrate_root(Namespace(repo=None))

    assert Path(root) == project.resolve()
    assert Path(root) != wt1.resolve()
