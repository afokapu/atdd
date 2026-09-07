# URN: test:govern-lifecycle:read-verbs-are-side-effect-free:C019-SMOKE-001-the-real-read-verb-mutates-nothing
# Acceptance: acc:govern-lifecycle:C019-SMOKE-001-the-real-read-verb-mutates-nothing
# WMBT: wmbt:govern-lifecycle:C019
# Phase: RED
# Layer: integration
"""C019-SMOKE-001 — the real read verb leaves git untouched.

The unit acceptances stub the GitHub reads, so they can only prove the decision.
This runs the real CLI and compares git's own branch and worktree listings before
and after, because the defect was a real branch created and PUSHED to a real
remote — a mutation only git can attest to.

Skips rather than passes when no suitable issue is available, so it never claims
to have observed something it could not see.

SHARP EDGE: run against UNFIXED code this test mutates the repository — that is
precisely the defect it detects. Proving it non-vacuous at origin/main created a
worktree for an unrelated live branch, which had to be cleaned up by hand. It is
safe on fixed code and as a regression guard; do not point it at a revision
predating the fix without expecting to clean up after it.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from atdd.coach.utils.repo import find_repo_root, is_atdd_source_repo

pytestmark = [pytest.mark.github_api, pytest.mark.platform]

_BRANCH_PHASES = ("PLANNED", "RED", "GREEN", "SMOKE", "REFACTOR")


def _git(root, *args) -> str:
    return subprocess.run(["git", *args], cwd=str(root), capture_output=True,
                          text=True, timeout=30).stdout


def _issue_without_worktree(root):
    """An open issue in a branch phase whose worktree is absent — the create path."""
    raw = subprocess.run(
        ["gh", "issue", "list", "--state", "open", "--limit", "60",
         "--json", "number,labels"],
        cwd=str(root), capture_output=True, text=True, timeout=60,
    ).stdout
    trees = _git(root, "worktree", "list")
    for item in json.loads(raw or "[]"):
        names = {l.get("name", "") for l in item.get("labels", [])}
        if not any(f"atdd:{p}" in names for p in _BRANCH_PHASES):
            continue
        if str(item["number"]) in trees:
            continue
        return item["number"]
    return None


def test_the_real_read_verb_mutates_nothing():
    if not is_atdd_source_repo():
        pytest.skip("toolkit-self acceptance; the real repository is the subject")

    root = find_repo_root()
    number = _issue_without_worktree(root)
    if number is None:
        pytest.skip("no open branch-phase issue lacking a worktree; nothing to observe")

    before = (_git(root, "branch", "--list"), _git(root, "worktree", "list"))

    # Run THIS checkout's code, not whatever `atdd` resolves to on PATH — an
    # installed CLI would answer for a different revision entirely.
    env = {**os.environ, "PYTHONPATH": str(root / "src")}
    proc = subprocess.run(
        [sys.executable, "-m", "atdd", "coach", "issues", str(number)],
        cwd=str(root), capture_output=True, text=True, timeout=300, env=env,
    )

    after = (_git(root, "branch", "--list"), _git(root, "worktree", "list"))

    assert proc.returncode == 0, (
        f"the read verb must exit 0 from any directory: {proc.stderr[-600:]}"
    )
    assert before[0] == after[0], (
        "`atdd coach issues` created or deleted a branch; a read verb must not"
    )
    assert before[1] == after[1], (
        "`atdd coach issues` created or removed a worktree; a read verb must not"
    )
