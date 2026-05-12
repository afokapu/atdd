# URN: test:coach-ops:pr-watcher-module:M001-INTEGRATION-004-agent-wait-ci-uses-watcher
# Acceptance: acc:coach-ops:M001-INTEGRATION-004-agent-wait-ci-uses-watcher
# WMBT: wmbt:coach-ops:M001
# Phase: RED
# Layer: integration
"""M001-INTEGRATION-004 — atdd agent wait-ci routes through pr_watcher.poll.

When an agent calls `atdd agent wait-ci --pr 101` it must use the batched
pr_watcher.poll() path — no direct per-PR gh pr view calls.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from atdd.coach.commands.agent import run_cli as run_agent_cli


_RATE_LIMIT_OK = json.dumps({"resources": {"graphql": {"remaining": 5000, "limit": 5000}}})
_PR_LIST_CLEAN = json.dumps([
    {"number": 101, "mergeStateStatus": "CLEAN"},
])
_PR_LIST_BLOCKED = json.dumps([
    {"number": 101, "mergeStateStatus": "BLOCKED"},
])


def test_agent_wait_ci_uses_poll_not_pr_view():
    pr_view_calls = [0]
    pr_list_calls = [0]

    def fake_run(cmd, **kwargs):
        cmd_str = " ".join(cmd)
        if "rate_limit" in cmd_str:
            r = MagicMock()
            r.returncode = 0
            r.stdout = _RATE_LIMIT_OK
            r.stderr = ""
            return r
        if "pr" in cmd_str and "list" in cmd_str:
            pr_list_calls[0] += 1
            r = MagicMock()
            r.returncode = 0
            r.stdout = _PR_LIST_CLEAN
            r.stderr = ""
            return r
        if "pr" in cmd_str and "view" in cmd_str:
            pr_view_calls[0] += 1
            r = MagicMock()
            r.returncode = 0
            r.stdout = "{}"
            r.stderr = ""
            return r
        r = MagicMock()
        r.returncode = 0
        r.stdout = ""
        r.stderr = ""
        return r

    with patch("atdd.coach.runtime.pr_watcher.subprocess.run", side_effect=fake_run):
        exit_code = run_agent_cli(["wait-ci", "--pr", "101"])

    assert pr_view_calls[0] == 0, "wait-ci must NOT call gh pr view directly"
    assert pr_list_calls[0] >= 1, "wait-ci must use gh pr list (batched poll)"
    assert exit_code == 0


def test_agent_wait_ci_exits_0_when_pr_is_clean(capsys):
    def fake_run(cmd, **kwargs):
        cmd_str = " ".join(cmd)
        if "rate_limit" in cmd_str:
            r = MagicMock()
            r.returncode = 0
            r.stdout = _RATE_LIMIT_OK
            r.stderr = ""
            return r
        r = MagicMock()
        r.returncode = 0
        r.stdout = _PR_LIST_CLEAN
        r.stderr = ""
        return r

    with patch("atdd.coach.runtime.pr_watcher.subprocess.run", side_effect=fake_run):
        exit_code = run_agent_cli(["wait-ci", "--pr", "101"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "101" in out
