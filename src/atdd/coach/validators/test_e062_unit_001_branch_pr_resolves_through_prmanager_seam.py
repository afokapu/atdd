# URN: test:govern-lifecycle:enforce-smoke-refactor-phase-substrate:E062-UNIT-001-branch-pr-resolves-through-prmanager-seam
# Acceptance: acc:govern-lifecycle:E062-UNIT-001-branch-pr-resolves-through-prmanager-seam
# WMBT: wmbt:govern-lifecycle:E062
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""E062-UNIT-001 — the branch leg of the current-PR resolver returns the PR number.

The E056 resolver called ``int()`` on ``PRManager._existing_pr_for_branch()``, which
returns a URL, so every branch resolution raised ValueError, was swallowed by a bare
``except Exception``, and returned None — silently degrading the gate to a repo-wide
block. Resolution now goes through one shared ``PRManager.pr_number_for_branch`` seam
that parses the URL GitHub actually returns.
"""
from __future__ import annotations

from typing import Optional

import pytest

from atdd.coach.commands.pr import PRManager
from atdd.coach.validators import test_pr_merge_blocks_pre_smoke_close as mod

# The exact shape `gh pr list --json number,url --jq .[0].url` returns.
_PR_URL = "https://github.com/afokapu/atdd/pull/1461"


def _manager(url: Optional[str], monkeypatch: pytest.MonkeyPatch) -> PRManager:
    """A PRManager whose gh boundary yields ``url`` for any branch."""
    mgr = PRManager(target_dir=None)
    monkeypatch.setattr(
        PRManager, "_existing_pr_for_branch", lambda self, branch: url, raising=True
    )
    return mgr


def test_pr_number_for_branch_parses_the_url_gh_returns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mgr = _manager(_PR_URL, monkeypatch)
    assert mgr.pr_number_for_branch("feat/some-branch") == 1461


def test_pr_number_for_branch_is_none_without_an_open_pr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mgr = _manager(None, monkeypatch)
    assert mgr.pr_number_for_branch("feat/no-pr-yet") is None


def test_current_pr_resolves_from_the_branch_with_no_ci_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The push-event path: no PR-shaped GITHUB_REF, so the branch leg must carry it.

    This is the case that reds every contributor's branch today — it returned None,
    and None meant "block repo-wide".
    """
    monkeypatch.delenv("ATDD_PR_NUMBER", raising=False)
    monkeypatch.delenv("PR_NUMBER", raising=False)
    monkeypatch.setenv("GITHUB_REF", "refs/heads/feat/some-branch")
    monkeypatch.setattr(
        PRManager, "_detect_branch", lambda self: "feat/some-branch", raising=True
    )
    monkeypatch.setattr(
        PRManager, "_existing_pr_for_branch", lambda self, branch: _PR_URL, raising=True
    )

    assert mod._current_pr_number() == 1461
