# URN: test:govern-lifecycle:R004-SMOKE-001-real-linked-worktree-recognized-worktree-ready
# Acceptance: acc:govern-lifecycle:R004-SMOKE-001-real-linked-worktree-recognized-worktree-ready
# WMBT: wmbt:govern-lifecycle:R004
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""SMOKE test for #720 — against REAL infrastructure, a real on-disk
flat-sibling layout must be recognised as worktree-ready end-to-end.

No mocks, no stubs, no network:
  * a real git repository (`git init`, real commit);
  * a real linked worktree added with real `git worktree add` (its `.git`
    is a real gitfile);
  * real `git rev-parse --git-common-dir` plumbing;
  * the real `detect_worktree_layout` function;
  * the real `atdd branch` CLI launched as a subprocess.

With no manifest entry the real `atdd branch` run exits past the layout
gate with "not found in manifest" — proving the gate accepted the repo
without any stub on the manifest lookup.

The subprocess runs with PYTHONPATH pointed at this worktree's `src/` so
it exercises the fix under review, not whatever `atdd` is pip-installed.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from atdd.coach.utils.repo import detect_worktree_layout

pytestmark = [pytest.mark.coach]

# tests -> utils -> coach -> atdd -> src
_SRC_ROOT = Path(__file__).resolve().parents[4]


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True
    ).stdout


def _make_flat_sibling_repo(tmp_path: Path) -> tuple[Path, Path]:
    """Create a real main/ primary checkout plus one real flat sibling worktree."""
    main = tmp_path / "main"
    main.mkdir()
    _git("init", str(main))
    _git("-C", str(main), "config", "user.email", "smoke@test.invalid")
    _git("-C", str(main), "config", "user.name", "Smoke Tester")
    (main / "README.md").write_text("seed\n")
    _git("-C", str(main), "add", ".")
    _git("-C", str(main), "commit", "-m", "init")
    worktree = tmp_path / "feat-demo"
    _git("-C", str(main), "worktree", "add", str(worktree), "-b", "feat/demo")
    return main, worktree


def test_r004_smoke_001_real_linked_worktree_recognized_worktree_ready(
    tmp_path: Path,
) -> None:
    main, worktree = _make_flat_sibling_repo(tmp_path)

    # 1. Real git plumbing: the linked worktree's common dir is owned by main/.
    common_raw = _git("-C", str(worktree), "rev-parse", "--git-common-dir").strip()
    common_dir = Path(common_raw)
    if not common_dir.is_absolute():
        common_dir = (worktree / common_dir).resolve()
    assert common_dir.parent == main.resolve()

    # 2. The real detector recognises the real linked sibling worktree.
    assert detect_worktree_layout(worktree) == "worktree-ready"
    assert detect_worktree_layout(main) == "worktree-ready"

    # 3. The real `atdd branch` CLI, run as a subprocess from inside the real
    #    linked worktree, must not exit on the layout precondition. With no
    #    manifest it exits past the gate at the manifest lookup instead.
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_SRC_ROOT)
    result = subprocess.run(
        [sys.executable, "-m", "atdd", "branch", "999"],
        cwd=worktree, capture_output=True, text=True, timeout=60, env=env,
    )
    combined = result.stdout + result.stderr

    assert "Repository layout is" not in combined
    assert "expected 'worktree-ready'" not in combined
    # The run reached the manifest lookup — i.e. it got past the layout gate.
    assert "not found in manifest" in combined
