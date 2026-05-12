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


def test_poll_makes_exactly_one_subprocess_call(mock_gh_pr_list_response):
    call_count = 0

    def fake_run(cmd, **kwargs):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        result.returncode = 0
        result.stdout = mock_gh_pr_list_response
        result.stderr = ""
        return result

    with patch("atdd.coach.runtime.pr_watcher.subprocess.run", side_effect=fake_run):
        result = poll(prs=[101, 102, 103, 104])

    assert call_count == 1, f"Expected 1 gh call, got {call_count}"


def test_poll_returns_dict_mapping_pr_to_merge_state(mock_gh_pr_list_response):
    def fake_run(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 0
        result.stdout = mock_gh_pr_list_response
        result.stderr = ""
        return result

    with patch("atdd.coach.runtime.pr_watcher.subprocess.run", side_effect=fake_run):
        result = poll(prs=[101, 102, 103, 104])

    assert result[101] == "CLEAN"
    assert result[102] == "BLOCKED"
    assert result[103] == "UNKNOWN"
    assert result[104] == "CLEAN"


def test_poll_uses_json_flag_with_number_and_merge_state(mock_gh_pr_list_response):
    captured_cmd = []

    def fake_run(cmd, **kwargs):
        captured_cmd.extend(cmd)
        result = MagicMock()
        result.returncode = 0
        result.stdout = mock_gh_pr_list_response
        result.stderr = ""
        return result

    with patch("atdd.coach.runtime.pr_watcher.subprocess.run", side_effect=fake_run):
        poll(prs=[101, 102])

    cmd_str = " ".join(captured_cmd)
    assert "--json" in cmd_str
    assert "mergeStateStatus" in cmd_str
    assert "number" in cmd_str
