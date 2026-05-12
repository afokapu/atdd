# URN: test:coach-ops:pr-watcher-module:U001-UNIT-001-batched-poll-single-api-call
# Acceptance: acc:coach-ops:U001-UNIT-001-batched-poll-single-api-call
# WMBT: wmbt:coach-ops:U001
# Phase: RED
# Layer: application
"""U001-UNIT-001 — poll(prs=[N1,N2,N3,N4]) issues exactly one gh pr list call.

Batching all PR status reads into a single gh pr list --json call is the
core invariant of pr_watcher.py. This test verifies that regardless of how
many PR numbers are passed to poll(), only one subprocess call is made.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from atdd.coach.runtime.pr_watcher import poll


@pytest.fixture()
def mock_gh_pr_list_response():
    return json.dumps([
        {"number": 101, "mergeStateStatus": "CLEAN"},
        {"number": 102, "mergeStateStatus": "BLOCKED"},
        {"number": 103, "mergeStateStatus": "UNKNOWN"},
        {"number": 104, "mergeStateStatus": "CLEAN"},
    ])


def test_poll_makes_exactly_one_gh_pr_list_call(mock_gh_pr_list_response):
    """The core invariant: N PRs → exactly 1 gh pr list call (not N calls)."""
    pr_list_call_count = 0

    def fake_run(cmd, **kwargs):
        nonlocal pr_list_call_count
        result = MagicMock()
        result.returncode = 0
        # rate_limit check — return high budget so poll proceeds
        if "rate_limit" in " ".join(cmd):
            result.stdout = json.dumps({"resources": {"graphql": {"remaining": 5000, "limit": 5000}}})
        else:
            pr_list_call_count += 1
            result.stdout = mock_gh_pr_list_response
        result.stderr = ""
        return result

    with patch("atdd.coach.runtime.pr_watcher.subprocess.run", side_effect=fake_run):
        result = poll(prs=[101, 102, 103, 104])

    assert pr_list_call_count == 1, (
        f"Expected 1 gh pr list call (regardless of PR count), got {pr_list_call_count}"
    )


def test_poll_returns_dict_mapping_pr_to_merge_state(mock_gh_pr_list_response):
    _RATE_OK = json.dumps({"resources": {"graphql": {"remaining": 5000, "limit": 5000}}})

    def fake_run(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 0
        result.stdout = _RATE_OK if "rate_limit" in " ".join(cmd) else mock_gh_pr_list_response
        result.stderr = ""
        return result

    with patch("atdd.coach.runtime.pr_watcher.subprocess.run", side_effect=fake_run):
        result = poll(prs=[101, 102, 103, 104])

    assert result[101] == "CLEAN"
    assert result[102] == "BLOCKED"
    assert result[103] == "UNKNOWN"
    assert result[104] == "CLEAN"


def test_poll_uses_json_flag_with_number_and_merge_state(mock_gh_pr_list_response):
    _RATE_OK = json.dumps({"resources": {"graphql": {"remaining": 5000, "limit": 5000}}})
    captured_pr_list_cmds: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 0
        if "rate_limit" in " ".join(cmd):
            result.stdout = _RATE_OK
        else:
            captured_pr_list_cmds.append(list(cmd))
            result.stdout = mock_gh_pr_list_response
        result.stderr = ""
        return result

    with patch("atdd.coach.runtime.pr_watcher.subprocess.run", side_effect=fake_run):
        poll(prs=[101, 102])

    assert len(captured_pr_list_cmds) == 1
    cmd_str = " ".join(captured_pr_list_cmds[0])
    assert "--json" in cmd_str
    assert "mergeStateStatus" in cmd_str
    assert "number" in cmd_str
