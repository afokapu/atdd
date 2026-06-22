# URN: test:state-store:state-cli:live-doctor-and-layout
# Issue: #1177 (#1168 Phase 1)
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""#1177 SMOKE — live end-to-end of the `atdd state` CLI surface.

Drives the real installed-form CLI (`python -m atdd state ...`) via subprocess
against real on-disk layouts (run-or-fail, no skip): single-repo doctor →
sibling-worktree doctor → layout --check rejects a per-worktree State Store →
ambiguous parent/child .atdd fails loudly with a non-zero exit.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3]


def _state(root_arg, *args):
    env = {"PYTHONPATH": str(_SRC), "PATH": os.environ.get("PATH", ""),
           "HOME": str(root_arg), "CI": "true"}
    return subprocess.run(
        [sys.executable, "-m", "atdd", "state", *args],
        cwd=str(root_arg), env=env, capture_output=True, text=True, timeout=60,
    )


def _mk_worktree(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / ".git").mkdir(exist_ok=True)
    return path


def _mk_atdd(path: Path) -> Path:
    # Real Control Root needs an initialized-root marker (#1179).
    (path / ".atdd").mkdir(parents=True, exist_ok=True)
    (path / ".atdd" / "config.yaml").write_text("x\n", encoding="utf-8")
    return path


def test_doctor_single_repo_live(tmp_path):
    repo = _mk_atdd(_mk_worktree(tmp_path / "repo"))
    r = _state(repo, "doctor", "--root", str(repo))
    assert r.returncode == 0, r.stderr
    out = r.stdout + r.stderr
    assert "Layout Mode:        single-repo" in out
    assert str(repo) in out


def test_doctor_sibling_worktree_live(tmp_path):
    project = _mk_atdd(tmp_path / "project")
    main = _mk_worktree(project / "main")
    r = _state(project, "doctor", "--root", str(main))
    assert r.returncode == 0, r.stderr
    out = r.stdout + r.stderr
    assert "sibling-worktree" in out
    assert str(project) in out          # Control Root is the parent
    assert str(main) in out             # Git worktree root is the child


def test_layout_check_rejects_per_worktree_store_live(tmp_path):
    project = _mk_atdd(tmp_path / "project")
    _mk_worktree(project / "main")
    rogue = _mk_worktree(project / "worktree1")
    store = rogue / ".atdd" / "state" / "state.sqlite"
    store.parent.mkdir(parents=True, exist_ok=True)
    store.touch()

    r = _state(project, "layout", "--check", "--root", str(project))
    assert r.returncode == 1, (r.returncode, r.stdout, r.stderr)
    assert "Per-worktree State Store" in (r.stdout + r.stderr)


def test_doctor_ambiguous_fails_loudly_live(tmp_path):
    project = _mk_atdd(tmp_path / "project")
    main = _mk_atdd(_mk_worktree(project / "main"))   # both parent + child .atdd/
    r = _state(project, "doctor", "--root", str(main))
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    assert "Ambiguous ATDD Control Root" in (r.stdout + r.stderr)
