# URN: test:govern-lifecycle:read-verbs-are-side-effect-free:C019-UNIT-002-the-callers-own-worktree-is-recognised
# Acceptance: acc:govern-lifecycle:C019-UNIT-002-the-callers-own-worktree-is-recognised
# WMBT: wmbt:govern-lifecycle:C019
# Phase: RED
# Layer: application
"""C019-UNIT-002 — the identity check must not be fooled by the prefix.

`_is_in_worktree` compared `target_dir.name` to a `{prefix}-{slug}` string
derived from the issue body. A worktree created with `--prefix fix` while the
body says `feat` is therefore unseen, and a duplicate is made beside it — which
is exactly what happened to #1802.
"""
from __future__ import annotations

from atdd.coach.commands.issue_lifecycle import IssueLifecycle


def _lifecycle_at(tmp_path, dir_name: str) -> IssueLifecycle:
    lc = IssueLifecycle()
    lc.target_dir = tmp_path / dir_name
    lc.target_dir.mkdir(parents=True, exist_ok=True)
    return lc


def test_a_different_prefix_is_still_the_issues_worktree(tmp_path):
    # Standing in fix-my-slug while the body derives prefix "feat".
    lc = _lifecycle_at(tmp_path, "fix-my-slug")

    assert lc._is_in_worktree("my-slug", "feat") is True, (
        "the caller is standing in this issue's worktree; the prefix it was "
        "created under must not make it invisible"
    )


def test_the_matching_prefix_still_works(tmp_path):
    lc = _lifecycle_at(tmp_path, "feat-my-slug")
    assert lc._is_in_worktree("my-slug", "feat") is True


def test_an_unrelated_directory_is_not_the_issues_worktree(tmp_path):
    # The guard against answering yes to everything.
    lc = _lifecycle_at(tmp_path, "fix-some-other-issue")
    assert lc._is_in_worktree("my-slug", "feat") is False
