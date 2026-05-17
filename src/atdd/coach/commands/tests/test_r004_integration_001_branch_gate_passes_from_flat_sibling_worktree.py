# URN: test:govern-lifecycle:R004-INTEGRATION-001-branch-gate-passes-from-flat-sibling-worktree
# Acceptance: acc:govern-lifecycle:R004-INTEGRATION-001-branch-gate-passes-from-flat-sibling-worktree
# WMBT: wmbt:govern-lifecycle:R004
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""RED test for #720 — BranchManager.branch() must not abort on the
worktree-layout precondition when invoked from inside a linked worktree of an
already flat-sibling repo.

`BranchManager.branch()` calls `detect_worktree_layout(self.target_dir)` and
returns 1 with "Repository layout is 'worktree', expected 'worktree-ready'"
for anything other than worktree-ready. Run from inside a legitimate flat
sibling worktree this falsely rejects the operation.

Here `_find_issue` is stubbed to return None so the run stops just past the
layout gate. This test FAILS today because the gate prints the layout error
before reaching the manifest lookup.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atdd.coach.commands.branch import BranchManager

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


def test_r004_integration_001_branch_gate_passes_from_flat_sibling_worktree(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _main, worktree = _make_flat_sibling_repo(tmp_path)

    manager = BranchManager(target_dir=worktree)
    # Stop the run right after the layout gate: with no manifest entry,
    # branch() returns 1 with "not found in manifest" once the gate passes.
    manager._find_issue = lambda issue_number: None  # type: ignore[method-assign]

    manager.branch(999)
    out = capsys.readouterr().out

    # RED: today the layout gate fires first and prints this error because the
    # linked worktree is misclassified as "worktree". After #720 the gate
    # passes and the run reaches the manifest lookup instead.
    assert "Repository layout is" not in out
    assert "expected 'worktree-ready'" not in out
