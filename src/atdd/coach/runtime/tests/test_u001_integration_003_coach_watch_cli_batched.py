# URN: test:coach-ops:pr-watcher-module:U001-INTEGRATION-003-coach-watch-cli-batched
# Acceptance: acc:coach-ops:U001-INTEGRATION-003-coach-watch-cli-batched
# WMBT: wmbt:coach-ops:U001
# Phase: RED
# Layer: integration
"""U001-INTEGRATION-003 — atdd coach watch with 4 PRs makes a single gh pr list call.

Verifies the CLI surface routes through pr_watcher and inherits its batching guarantee.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from atdd.coach.commands.coach_watch import run_watch


_RATE_LIMIT_OK = json.dumps({"resources": {"graphql": {"remaining": 5000, "limit": 5000}}})
_PR_LIST = json.dumps([
    {"number": 101, "mergeStateStatus": "CLEAN"},
    {"number": 102, "mergeStateStatus": "BLOCKED"},
    {"number": 103, "mergeStateStatus": "UNKNOWN"},
    {"number": 104, "mergeStateStatus": "CLEAN"},
])


def test_watch_makes_one_gh_pr_list_call():
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
            r.stdout = _PR_LIST
            r.stderr = ""
            return r
        r = MagicMock()
        r.returncode = 0
        r.stdout = ""
        r.stderr = ""
        return r

    with patch("atdd.coach.runtime.pr_watcher.subprocess.run", side_effect=fake_run):
        exit_code = run_watch(["101", "102", "103", "104"])

    assert pr_list_calls[0] == 1, f"Expected 1 pr list call, got {pr_list_calls[0]}"
    assert exit_code == 0


def test_watch_output_contains_status_for_each_pr(capsys):
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
        r.stdout = _PR_LIST
        r.stderr = ""
        return r

    with patch("atdd.coach.runtime.pr_watcher.subprocess.run", side_effect=fake_run):
        run_watch(["101", "102", "103", "104"])

    out = capsys.readouterr().out
    assert "101" in out
    assert "102" in out
    assert "103" in out
    assert "104" in out
