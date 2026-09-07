# URN: test:author-atdd-substrate:author-issue-body:C013-SMOKE-001-a-real-deletion-in-this-repos-history
# Acceptance: acc:author-atdd-substrate:C013-SMOKE-001-a-real-deletion-in-this-repos-history
# WMBT: wmbt:author-atdd-substrate:C013
# Phase: RED
# Layer: integration
"""C013-SMOKE-001 — against this repository's own history.

The unit acceptances build a two-commit repo. This asks the same question of a
real commit here, where merges, renames and squashes make history messier than
any fixture. Skips if no such commit is reachable.
"""
from __future__ import annotations

import subprocess

import pytest

from atdd.coach.commands.issue import IssueManager
from atdd.coach.utils.repo import find_repo_root, is_atdd_source_repo

pytestmark = [pytest.mark.platform]


def test_a_real_deletion_in_this_repos_history():
    if not is_atdd_source_repo():
        pytest.skip("toolkit-self acceptance; this repository's history is the subject")
    root = find_repo_root()

    def git(*a):
        return subprocess.run(["git", *a], cwd=str(root), capture_output=True,
                              text=True, timeout=60).stdout.strip()

    commit = git("log", "--diff-filter=D", "--format=%H", "-1", "--", "src/")
    if not commit:
        pytest.skip("no commit deleting a tracked file under src/ is reachable")
    deleted = git("diff", "--diff-filter=D", "--name-only", f"{commit}^", commit, "--", "src/").splitlines()
    if not deleted:
        pytest.skip("could not read the deleted path for that commit")

    mgr = IssueManager()
    mgr.target_dir = root

    assert mgr._artifact_resolves("deleted", deleted[0], commit) is True, (
        f"{deleted[0]} was deleted by {commit[:8]} in this repository's own history"
    )
    assert mgr._artifact_resolves("deleted", "never/existed/here.txt", commit) is False, (
        "a path this repository never held must not resolve as CONFIRMED GONE"
    )
