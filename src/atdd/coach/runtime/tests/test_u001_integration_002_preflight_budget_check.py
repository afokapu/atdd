# URN: test:coach-ops:pr-watcher-module:U001-INTEGRATION-002-preflight-budget-check
# Acceptance: acc:coach-ops:U001-INTEGRATION-002-preflight-budget-check
# WMBT: wmbt:coach-ops:U001
# Phase: RED
# Layer: integration
"""U001-INTEGRATION-002 — <500 graphql points remaining → poll cycle skipped, notified once.

When the pre-flight gh api rate_limit check returns fewer than 500 remaining
graphql points, pr_watcher must skip the poll cycle and notify the operator
exactly once (not spam on every invocation while budget is low).
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from atdd.coach.runtime.pr_watcher import PRWatcher


_LOW_BUDGET_RESPONSE = json.dumps({
    "resources": {"graphql": {"remaining": 450, "limit": 5000}}
})
_OK_BUDGET_RESPONSE = json.dumps({
    "resources": {"graphql": {"remaining": 5000, "limit": 5000}}
})
_PR_LIST_RESPONSE = json.dumps([
    {"number": 10, "mergeStateStatus": "CLEAN"},
])


def _build_fake_run(rate_limit_body: str):
    def fake_run(cmd, **kwargs):
        if "rate_limit" in " ".join(cmd):
            r = MagicMock()
            r.returncode = 0
            r.stdout = rate_limit_body
            r.stderr = ""
            return r
        r = MagicMock()
        r.returncode = 0
        r.stdout = _PR_LIST_RESPONSE
        r.stderr = ""
        return r
    return fake_run


def test_poll_skipped_when_budget_below_threshold():
    pr_list_calls = [0]

    def fake_run(cmd, **kwargs):
        if "rate_limit" in " ".join(cmd):
            r = MagicMock()
            r.returncode = 0
            r.stdout = _LOW_BUDGET_RESPONSE
            r.stderr = ""
            return r
        pr_list_calls[0] += 1
        r = MagicMock()
        r.returncode = 0
        r.stdout = _PR_LIST_RESPONSE
        r.stderr = ""
        return r

    watcher = PRWatcher(repo="owner/repo", poll_interval=180)

    with patch("atdd.coach.runtime.pr_watcher.subprocess.run", side_effect=fake_run):
        result = watcher.poll(prs=[10])

    assert pr_list_calls[0] == 0, "gh pr list must NOT be called when budget < 500"
    assert result == {} or result is None, "Skipped poll should return empty/None"


def test_budget_warning_emitted_once_not_on_every_low_budget_call(capsys):
    watcher = PRWatcher(repo="owner/repo", poll_interval=180)

    with patch("atdd.coach.runtime.pr_watcher.subprocess.run", side_effect=_build_fake_run(_LOW_BUDGET_RESPONSE)):
        watcher.poll(prs=[10])
        watcher.poll(prs=[10])
        watcher.poll(prs=[10])

    captured = capsys.readouterr()
    warning_count = captured.out.count("rate limit") + captured.err.count("rate limit")
    assert warning_count <= 1, (
        f"Budget warning should appear at most once, appeared {warning_count} times"
    )


def test_poll_proceeds_when_budget_is_sufficient():
    pr_list_calls = [0]

    def fake_run(cmd, **kwargs):
        if "rate_limit" in " ".join(cmd):
            r = MagicMock()
            r.returncode = 0
            r.stdout = _OK_BUDGET_RESPONSE
            r.stderr = ""
            return r
        pr_list_calls[0] += 1
        r = MagicMock()
        r.returncode = 0
        r.stdout = _PR_LIST_RESPONSE
        r.stderr = ""
        return r

    watcher = PRWatcher(repo="owner/repo", poll_interval=180)

    with patch("atdd.coach.runtime.pr_watcher.subprocess.run", side_effect=fake_run):
        result = watcher.poll(prs=[10])

    assert pr_list_calls[0] == 1, "gh pr list should be called when budget >= 500"
    assert result == {10: "CLEAN"}
