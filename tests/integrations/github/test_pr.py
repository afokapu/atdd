"""Fixture-based tests for ``atdd.integrations.github.pr`` (no live API)."""
from __future__ import annotations

import json

from atdd.integrations.github import _gh, pr
from atdd.integrations.github.types import GitHubIntegrationError

PR_VIEW_JSON = json.dumps({
    "number": 950,
    "state": "OPEN",
    "mergeable": "MERGEABLE",
    "mergeStateStatus": "CLEAN",
    "headRefOid": "abc123",
    "statusCheckRollup": [
        {"name": "ATDD Validate", "conclusion": "SUCCESS"},
        {"name": "lint", "status": "IN_PROGRESS"},
    ],
    "reviews": [
        {"author": {"login": "octocat"}, "state": "APPROVED",
         "submittedAt": "2026-05-31T00:00:00Z"},
    ],
    "closingIssuesReferences": [{"number": 891}],
})


def test_read_pr_state_parses_rollup_reviews_and_closes(monkeypatch):
    monkeypatch.setattr(
        _gh, "run_gh",
        lambda args, **kw: PR_VIEW_JSON,
    )
    state = pr.read_pr_state(950)
    assert state.number == 950
    assert state.state == "OPEN"
    assert state.merge_state == "CLEAN"
    assert state.head_sha == "abc123"
    assert state.closes_issues == (891,)
    names = {c.name: c.conclusion for c in state.check_runs}
    assert names["ATDD Validate"] == "SUCCESS"
    assert names["lint"] == "IN_PROGRESS"  # running check surfaces its status
    assert state.reviews[0].reviewer == "octocat"
    assert state.reviews[0].state == "APPROVED"


def test_merge_pr_failure_returns_unmerged(monkeypatch):
    def boom(args, **kw):
        raise GitHubIntegrationError("gh command failed: pr merge\nstderr: not mergeable")
    monkeypatch.setattr(_gh, "run_gh", boom)

    result = pr.merge_pr(950, strategy="squash")
    assert result.merged is False
    assert "not mergeable" in result.reason


def test_merge_pr_success_reads_merge_commit(monkeypatch):
    def fake(args, **kw):
        if args[:2] == ["pr", "merge"]:
            return ""
        if args[:2] == ["pr", "view"]:
            return "deadbeef"
        return ""
    monkeypatch.setattr(_gh, "run_gh", fake)

    result = pr.merge_pr(950, strategy="squash")
    assert result.merged is True
    assert result.merge_commit_sha == "deadbeef"
