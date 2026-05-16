# URN: test:govern-lifecycle:R004-SMOKE-001-real-linked-worktree-recognized-worktree-ready
# Acceptance: acc:govern-lifecycle:R004-SMOKE-001-real-linked-worktree-recognized-worktree-ready
# WMBT: wmbt:govern-lifecycle:R004
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""RED SMOKE test for #720 — against real git plumbing, a real on-disk
flat-sibling layout (real `git init`, real `git worktree add`) must be
recognised as worktree-ready end-to-end so the real `atdd branch` precondition
does not reject it.

This exercises real infrastructure: a real git repository, a real linked
worktree whose `.git` is a real gitfile, and the real
`git rev-parse --git-common-dir` plumbing — no stubs, no network.

This test FAILS today: detect_worktree_layout returns "worktree" for the real
linked sibling worktree and the real BranchManager gate prints the layout
rejection.
"""
from __future__ import annotations

import contextlib
import io
import subprocess
from pathlib import Path

import pytest

from atdd.coach.commands.branch import BranchManager
from atdd.coach.utils.repo import detect_worktree_layout

pytestmark = [pytest.mark.coach]


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True
    ).stdout


def _make_flat_sibling_repo(tmp_path: Path) -> tuple[Path, Path]:
    """Create a main/ primary checkout plus one real flat sibling worktree."""
    main = tmp_path / "main"
    main.mkdir()
    _git("init", str(main))
    _git("-C", str(main), "config", "user.email", "t@t.test")
    _git("-C", str(main), "config", "user.name", "Tester")
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

    # Real git plumbing: the linked worktree's common dir is owned by main/.
    common_raw = _git("-C", str(worktree), "rev-parse", "--git-common-dir").strip()
    common_dir = Path(common_raw)
    if not common_dir.is_absolute():
        common_dir = (worktree / common_dir).resolve()
    assert common_dir.parent == main.resolve()

    # RED: the detector must recognise the real linked sibling worktree as
    # worktree-ready; today it returns "worktree".
    assert detect_worktree_layout(worktree) == "worktree-ready"

    # RED: the real `atdd branch` precondition gate must not reject the real
    # linked worktree. _find_issue is stubbed to None so branch() stops just
    # past the gate without any network call.
    manager = BranchManager(target_dir=worktree)
    manager._find_issue = lambda issue_number: None  # type: ignore[method-assign]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        manager.branch(999)
    assert "Repository layout is" not in buf.getvalue()
