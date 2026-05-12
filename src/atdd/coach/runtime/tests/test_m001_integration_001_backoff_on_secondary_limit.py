# URN: test:coach-ops:pr-watcher-module:M001-INTEGRATION-001-backoff-on-secondary-limit
# Acceptance: acc:coach-ops:M001-INTEGRATION-001-backoff-on-secondary-limit
# WMBT: wmbt:coach-ops:M001
# Phase: RED
# Layer: integration
"""M001-INTEGRATION-001 — 403 abuse response triggers exponential backoff 180s→600s→1200s.

When gh returns a secondary rate-limit / 403-abuse error, pr_watcher must
back off exponentially: first failure → 600s sleep, second → 1200s, then
recover to normal on next success.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from atdd.coach.runtime.pr_watcher import PRWatcher


_SUCCESS_RESPONSE = json.dumps([
    {"number": 10, "mergeStateStatus": "CLEAN"},
])

_RATE_LIMIT_RESPONSE = json.dumps({"resources": {"graphql": {"remaining": 5000, "limit": 5000}}})


def _make_secondary_limit_error():
    """Simulates gh returning a secondary rate-limit (403 abuse) error."""
    r = MagicMock()
    r.returncode = 1
    r.stdout = ""
    r.stderr = "error: secondary rate limit"
    return r


def test_backoff_sequence_on_secondary_limit():
    sleep_calls: list[float] = []
    call_count = [0]

    def fake_run(cmd, **kwargs):
        # rate_limit calls always succeed
        if "rate_limit" in " ".join(cmd):
            r = MagicMock()
            r.returncode = 0
            r.stdout = _RATE_LIMIT_RESPONSE
            r.stderr = ""
            return r
        call_count[0] += 1
        if call_count[0] <= 2:
            return _make_secondary_limit_error()
        r = MagicMock()
        r.returncode = 0
        r.stdout = _SUCCESS_RESPONSE
        r.stderr = ""
        return r

    watcher = PRWatcher(repo="owner/repo", poll_interval=180)

    with patch("atdd.coach.runtime.pr_watcher.subprocess.run", side_effect=fake_run):
        with patch("atdd.coach.runtime.pr_watcher.time.sleep", side_effect=lambda s: sleep_calls.append(s)):
            result1 = watcher.poll(prs=[10])
            result2 = watcher.poll(prs=[10])
            result3 = watcher.poll(prs=[10])

    assert sleep_calls[0] == 600, f"First backoff should be 600s, got {sleep_calls[0]}"
    assert sleep_calls[1] == 1200, f"Second backoff should be 1200s, got {sleep_calls[1]}"
    assert result3 == {10: "CLEAN"}


def test_backoff_resets_after_successful_poll():
    sleep_calls: list[float] = []
    call_count = [0]

    def fake_run(cmd, **kwargs):
        if "rate_limit" in " ".join(cmd):
            r = MagicMock()
            r.returncode = 0
            r.stdout = _RATE_LIMIT_RESPONSE
            r.stderr = ""
            return r
        call_count[0] += 1
        if call_count[0] == 1:
            return _make_secondary_limit_error()
        r = MagicMock()
        r.returncode = 0
        r.stdout = _SUCCESS_RESPONSE
        r.stderr = ""
        return r

    watcher = PRWatcher(repo="owner/repo", poll_interval=180)

    with patch("atdd.coach.runtime.pr_watcher.subprocess.run", side_effect=fake_run):
        with patch("atdd.coach.runtime.pr_watcher.time.sleep", side_effect=lambda s: sleep_calls.append(s)):
            watcher.poll(prs=[10])  # triggers first backoff (600s)
            watcher.poll(prs=[10])  # succeeds — resets backoff
            watcher.poll(prs=[10])  # another success, no extra sleep

    # First failure → 600s. After reset, no additional backoff sleeps.
    assert sleep_calls == [600], f"Expected only one backoff sleep, got {sleep_calls}"
