# URN: test:self-compliance:smoke-gate-head:HEADRES-UNIT-001-smoke-gate-reads-the-issue-branch-head
# Phase: RED
# Layer: unit
# Assertion: behavioral
# Runtime: python
"""HEADRES-UNIT-001 — the staleness clause judges the issue's branch, not the cwd.

    `_head_sha` resolves the commit through the issue's store binding, so the
    answer does not depend on which directory the operator was standing in.

Observed three times on #1664: `atdd coach approve 1664 --transition
'SMOKE->REFACTOR'` from `~/Github/atdd/main` refused with

    smoke_stale_commit: the only passing smoke run(s) were captured at
    ['8adced115a67'], not at HEAD ac675ab80917

where `ac675ab80917` is origin/main — the HEAD of the invoking directory — and
`8adced115a67` is the issue's branch head. The identical command from the
issue's worktree succeeded. The store binding was correct throughout.

#1765 fixed the mint's own `resolve_head` and put this function in Out of Scope:
"it is deliberately separate and is not the defect". That holds for the mint and
not for the staleness clause, which asks whether the code that was smoked is the
code being advanced — and the code being advanced is the issue's branch, never
the directory the operator occupies. In a flat-sibling worktree layout those
differ as the normal case.

`refs/heads/<branch>` is shared by every worktree of a repository, so resolving
through it is cwd-independent by construction. That is the same seam #1765 chose.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atdd.coach.gate import smoke_execution_check as mod


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """A real repo with `main` and a feature branch at different commits."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    (root / "a.txt").write_text("one\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "on main")
    _git(root, "checkout", "-q", "-b", "feat/work")
    (root / "b.txt").write_text("two\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "on the branch")
    _git(root, "checkout", "-q", "main")
    return root


def test_head_of_the_issue_branch_is_not_the_head_of_the_cwd(repo: Path) -> None:
    """The premise: standing in main, the branch head differs. Guards the fixture."""
    assert _git(repo, "rev-parse", "HEAD") != _git(repo, "rev-parse", "refs/heads/feat/work")


def test_resolves_the_branch_head_while_standing_on_main(repo: Path) -> None:
    got = mod._head_sha(repo, branch="feat/work")
    assert got == _git(repo, "rev-parse", "refs/heads/feat/work"), (
        "the staleness clause must judge the commit being advanced, not the "
        "commit the operator happens to be standing on"
    )


def test_unresolvable_branch_returns_none_rather_than_the_cwd_head(repo: Path) -> None:
    """`None` relaxes only staleness; silently falling back to the cwd HEAD would
    reintroduce the defect while looking like it had been fixed."""
    got = mod._head_sha(repo, branch="feat/does-not-exist")
    assert got is None


def test_no_branch_falls_back_to_the_cwd_head(repo: Path) -> None:
    """Back-compat: callers that cannot name a branch keep today's behaviour."""
    assert mod._head_sha(repo, branch=None) == _git(repo, "rev-parse", "HEAD")
