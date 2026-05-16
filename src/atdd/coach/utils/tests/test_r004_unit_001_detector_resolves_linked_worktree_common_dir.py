# URN: test:govern-lifecycle:R004-UNIT-001-detector-resolves-linked-worktree-common-dir
# Acceptance: acc:govern-lifecycle:R004-UNIT-001-detector-resolves-linked-worktree-common-dir
# WMBT: wmbt:govern-lifecycle:R004
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""RED test for #720 — detect_worktree_layout must resolve a linked worktree's
git-common-dir back to a main/ primary checkout.

A repository in flat-sibling layout has its primary checkout in main/ and each
branch as a flat sibling worktree (`.git` is a gitfile). detect_worktree_layout
currently returns "worktree" for ANY linked worktree without resolving
`git rev-parse --git-common-dir`, so a correctly-laid-out repo is misclassified
and the `atdd branch` precondition gate aborts.

This test FAILS until the detector resolves the common dir: today
detect_worktree_layout(<linked sibling worktree>) returns "worktree", not
"worktree-ready".
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atdd.coach.utils.repo import detect_worktree_layout

pytestmark = [pytest.mark.coach]


def _git(*args: str) -> None:
    subprocess.run(["git", *args], check=True, capture_output=True, text=True)


def _make_flat_sibling_repo(tmp_path: Path) -> tuple[Path, Path]:
    """Create a main/ primary checkout plus one flat sibling linked worktree."""
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


def _make_plain_repo(path: Path) -> Path:
    """Create a single-directory git repo whose dir is NOT named main/."""
    path.mkdir()
    _git("init", str(path))
    return path


def test_r004_unit_001_detector_resolves_linked_worktree_common_dir(tmp_path: Path) -> None:
    main, worktree = _make_flat_sibling_repo(tmp_path)
    legacy = _make_plain_repo(tmp_path / "legacy-project")
    nogit = tmp_path / "bare-dir"
    nogit.mkdir()

    # The main/ primary checkout is worktree-ready (unchanged behaviour).
    assert detect_worktree_layout(main) == "worktree-ready"

    # RED: a linked sibling worktree of a flat-sibling layout is ALSO
    # worktree-ready — its git-common-dir parent is named main/.
    # Today the detector returns "worktree" because it never resolves the
    # common dir, so this assertion fails until #720 is fixed.
    assert detect_worktree_layout(worktree) == "worktree-ready"

    # A genuinely-unmigrated single checkout stays "flat" (unchanged behaviour).
    assert detect_worktree_layout(legacy) == "flat"

    # A directory with no .git stays "no-git" (unchanged behaviour).
    assert detect_worktree_layout(nogit) == "no-git"
