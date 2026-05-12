# URN: test:coach-ops:pr-watcher-module:M001-UNIT-002-cheap-state-default
# Acceptance: acc:coach-ops:M001-UNIT-002-cheap-state-default
# WMBT: wmbt:coach-ops:M001
# Phase: RED
# Layer: application
"""M001-UNIT-002 — default poll contains mergeStateStatus only, no statusCheckRollup.

The expensive statusCheckRollup expansion is deferred entirely to failures().
poll() must never include it, even implicitly.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from atdd.coach.runtime.pr_watcher import poll


_RATE_OK = json.dumps({"resources": {"graphql": {"remaining": 5000, "limit": 5000}}})


def _make_fake_run(response_body: str):
    def fake_run(cmd, **kwargs):
        r = MagicMock()
        r.returncode = 0
        r.stdout = _RATE_OK if "rate_limit" in " ".join(cmd) else response_body
        r.stderr = ""
        return r
    return fake_run


def test_poll_response_values_are_plain_strings():
    raw = json.dumps([{"number": 55, "mergeStateStatus": "CLEAN"}])
    with patch("atdd.coach.runtime.pr_watcher.subprocess.run", side_effect=_make_fake_run(raw)):
        result = poll(prs=[55])

    assert isinstance(result[55], str), "mergeStateStatus should be a plain string"


def test_poll_command_does_not_include_status_check_rollup():
    pr_list_cmds: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        r = MagicMock()
        r.returncode = 0
        if "rate_limit" in " ".join(cmd):
            r.stdout = _RATE_OK
        else:
            pr_list_cmds.append(list(cmd))
            r.stdout = json.dumps([{"number": 55, "mergeStateStatus": "CLEAN"}])
        r.stderr = ""
        return r

    with patch("atdd.coach.runtime.pr_watcher.subprocess.run", side_effect=fake_run):
        poll(prs=[55])

    assert len(pr_list_cmds) == 1
    cmd_str = " ".join(pr_list_cmds[0])
    assert "statusCheckRollup" not in cmd_str, (
        "poll() must not request statusCheckRollup in the default call"
    )


def test_poll_single_pr_returns_dict_with_one_entry():
    raw = json.dumps([{"number": 99, "mergeStateStatus": "BLOCKED"}])
    with patch("atdd.coach.runtime.pr_watcher.subprocess.run", side_effect=_make_fake_run(raw)):
        result = poll(prs=[99])

    assert list(result.keys()) == [99]
    assert result[99] == "BLOCKED"
