# URN: test:govern-lifecycle:R004-INTEGRATION-003-issue-reenter-create-branch-passes
# Acceptance: acc:govern-lifecycle:R004-INTEGRATION-003-issue-reenter-create-branch-passes
# WMBT: wmbt:govern-lifecycle:R004
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""RED test for #720 — the `atdd issue <N>` re-enter lifecycle path
(IssueLifecycle._create_branch -> BranchManager.branch) must not abort on the
worktree-layout gate when run from a linked worktree of an already
flat-sibling repo.

IssueLifecycle._create_branch constructs BranchManager(self.target_dir) and,
when the issue is in the manifest, calls manager.branch() — which runs the
layout precondition. With target_dir a linked sibling worktree, the detector
returns "worktree" today and the gate rejects the lifecycle path.

This test FAILS today on the detector assertion: detect_worktree_layout for
the linked worktree returns "worktree", not "worktree-ready".
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atdd.coach.commands import branch as branch_mod
from atdd.coach.commands.issue_lifecycle import IssueLifecycle
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
    worktree = tmp_path / "chore-demo"
    _git("-C", str(main), "worktree", "add", str(worktree), "-b", "chore/demo")
    return main, worktree


def test_r004_integration_003_issue_reenter_create_branch_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _main, worktree = _make_flat_sibling_repo(tmp_path)

    branch_calls: list[int] = []

    def _spy_branch(self, issue_number: int, prefix=None) -> int:  # noqa: ANN001
        branch_calls.append(issue_number)
        return 0

    # _find_issue must return an entry so _create_branch routes through
    # BranchManager.branch() (the gated path) rather than the direct fallback.
    monkeypatch.setattr(
        branch_mod.BranchManager, "_find_issue",
        lambda self, n: {"slug": "demo", "issue_number": n},
    )
    monkeypatch.setattr(branch_mod.BranchManager, "branch", _spy_branch)

    lifecycle = IssueLifecycle(target_dir=worktree)
    lifecycle._create_branch(720, "demo", "chore")

    # RED: the lifecycle path resolves the linked worktree via
    # detect_worktree_layout; today it returns "worktree" so the BranchManager
    # gate would reject it. After #720 it resolves to "worktree-ready".
    assert detect_worktree_layout(worktree) == "worktree-ready"

    # The lifecycle path reaches BranchManager.branch (no early short-circuit).
    assert branch_calls == [720]
