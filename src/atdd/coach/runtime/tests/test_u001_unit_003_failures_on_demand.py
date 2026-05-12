# URN: test:coach-ops:pr-watcher-module:U001-UNIT-003-failures-on-demand
# Acceptance: acc:coach-ops:U001-UNIT-003-failures-on-demand
# WMBT: wmbt:coach-ops:U001
# Phase: RED
# Layer: application
"""U001-UNIT-003 — failures(pr) fetches statusCheckRollup for ONE PR only when called.

statusCheckRollup is expensive; it must only be fetched when the caller
explicitly asks for failure diagnostics via pr_watcher.failures(pr).
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, call, patch

import pytest

from atdd.coach.runtime.pr_watcher import failures


_ROLLUP_RESPONSE = json.dumps({
    "statusCheckRollup": [
        {"name": "ci/test", "conclusion": "FAILURE", "detailsUrl": "https://example.com/1"},
        {"name": "ci/lint", "conclusion": "SUCCESS", "detailsUrl": "https://example.com/2"},
    ]
})


def test_failures_returns_list_of_failing_check_names():
    def fake_run(cmd, **kwargs):
        r = MagicMock()
        r.returncode = 0
        r.stdout = _ROLLUP_RESPONSE
        r.stderr = ""
        return r

    with patch("atdd.coach.runtime.pr_watcher.subprocess.run", side_effect=fake_run) as mock_run:
        result = failures(pr=101)

    assert result == ["ci/test"], f"Expected ['ci/test'], got {result!r}"


def test_failures_makes_exactly_one_gh_pr_view_call():
    def fake_run(cmd, **kwargs):
        r = MagicMock()
        r.returncode = 0
        r.stdout = _ROLLUP_RESPONSE
        r.stderr = ""
        return r

    with patch("atdd.coach.runtime.pr_watcher.subprocess.run", side_effect=fake_run) as mock_run:
        failures(pr=101)

    assert mock_run.call_count == 1


def test_failures_calls_gh_pr_view_with_status_check_rollup():
    captured_cmds: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        captured_cmds.append(list(cmd))
        r = MagicMock()
        r.returncode = 0
        r.stdout = _ROLLUP_RESPONSE
        r.stderr = ""
        return r

    with patch("atdd.coach.runtime.pr_watcher.subprocess.run", side_effect=fake_run):
        failures(pr=101)

    assert len(captured_cmds) == 1
    cmd_str = " ".join(captured_cmds[0])
    assert "statusCheckRollup" in cmd_str
    assert "101" in cmd_str


def test_failures_returns_empty_list_when_no_failures():
    all_pass = json.dumps({
        "statusCheckRollup": [
            {"name": "ci/test", "conclusion": "SUCCESS", "detailsUrl": ""},
        ]
    })

    def fake_run(cmd, **kwargs):
        r = MagicMock()
        r.returncode = 0
        r.stdout = all_pass
        r.stderr = ""
        return r

    with patch("atdd.coach.runtime.pr_watcher.subprocess.run", side_effect=fake_run):
        result = failures(pr=200)

    assert result == []
