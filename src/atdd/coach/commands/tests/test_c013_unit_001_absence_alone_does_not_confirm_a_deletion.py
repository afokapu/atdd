# URN: test:author-atdd-substrate:author-issue-body:C013-UNIT-001-absence-alone-does-not-confirm-a-deletion
# Acceptance: acc:author-atdd-substrate:C013-UNIT-001-absence-alone-does-not-confirm-a-deletion
# WMBT: wmbt:author-atdd-substrate:C013
# Phase: RED
# Layer: application
"""C013-UNIT-001 — a Deleted claim must name something the revision deleted.

The gate asked `git ls-tree <rev> -- <path>` and read EMPTY output as proof of
deletion. Emptiness is also what a path that never existed produces, so prose
and typos resolved as CONFIRMED GONE.

Driven against a real throwaway repository rather than a mocked subprocess: the
whole question is what git actually answers.
"""
from __future__ import annotations

import subprocess

import pytest

from atdd.coach.commands.issue import IssueManager


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)


@pytest.fixture
def repo_with_a_deletion(tmp_path):
    """A repo whose HEAD commit deleted `gone.txt` and left `kept.txt` alone."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "gone.txt").write_text("x")
    (tmp_path / "kept.txt").write_text("y")
    _git(tmp_path, "add", "-A"); _git(tmp_path, "commit", "-qm", "seed")
    (tmp_path / "gone.txt").unlink()
    (tmp_path / "kept.txt").write_text("y2")
    _git(tmp_path, "add", "-A"); _git(tmp_path, "commit", "-qm", "delete gone.txt")
    head = _git(tmp_path, "rev-parse", "HEAD").stdout.strip()
    return tmp_path, head


def _resolves(repo, landed, path):
    mgr = IssueManager()
    mgr.target_dir = repo
    return mgr._artifact_resolves("deleted", path, landed)


def test_a_genuinely_deleted_file_resolves(repo_with_a_deletion):
    repo, head = repo_with_a_deletion
    assert _resolves(repo, head, "gone.txt") is True, (
        "a real deletion must still be declarable, or the fix would break the "
        "legitimate case it exists to verify"
    )


def test_a_path_that_never_existed_does_not_resolve(repo_with_a_deletion):
    repo, head = repo_with_a_deletion
    assert _resolves(repo, head, "never/existed.txt") is False, (
        "the revision deleted nothing of that name; absence is not evidence of "
        "deletion, and treating it as such is what let prose earn CONFIRMED GONE"
    )


def test_a_file_left_in_place_does_not_resolve(repo_with_a_deletion):
    """The pre-existing negative, preserved."""
    repo, head = repo_with_a_deletion
    assert _resolves(repo, head, "kept.txt") is False
