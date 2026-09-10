# URN: test:govern-lifecycle:issue-fetch-separates-absent-from-unavailable:E074-UNIT-002-fetch-issue-reports-the-real-cause
# Acceptance: acc:govern-lifecycle:E074-UNIT-002-fetch-issue-reports-the-real-cause
# WMBT: wmbt:govern-lifecycle:E074
# Phase: GREEN
# Layer: backend.unit
"""E074-UNIT-002 — `_fetch_issue` records WHY it failed, and the caller's message
reflects it (#1895).

Drives the real method against a stubbed `gh` on PATH, because the defect was in
the seam between the subprocess result and the sentence the operator reads. A
test of the classifier alone would have passed while `_fetch_issue` went on
discarding the stderr.

The stub emits strings captured from real failures. It exits 1 for every failure,
exactly as `gh` does — the whole difficulty is that the return code carries no
information.
"""
from __future__ import annotations

import os
import stat

import pytest

from atdd.coach.commands.issue_lifecycle import IssueLifecycle
from atdd.coach.utils import gh_failure

_STUB = """#!/usr/bin/env bash
case "${LAB_GH_MODE}" in
  ok)         echo '{"number":1,"title":"t","state":"OPEN","labels":[],"body":"b"}'; exit 0 ;;
  not_found)  echo 'GraphQL: Could not resolve to an issue or pull request with the number of 99999999. (repository.issue)' >&2; exit 1 ;;
  rate_limit) echo 'GraphQL: API rate limit already exceeded for user ID 8843832.' >&2; exit 1 ;;
  network)    echo 'error connecting to api.github.com: dial tcp: lookup api.github.com: no such host' >&2; exit 1 ;;
  garbage)    echo 'not json at all'; exit 0 ;;
esac
"""


@pytest.fixture()
def with_stub_gh(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "gh"
    stub.write_text(_STUB, encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")

    def _set(mode: str):
        monkeypatch.setenv("LAB_GH_MODE", mode)
        return IssueLifecycle()

    return _set


def test_a_successful_fetch_records_no_failure(with_stub_gh) -> None:
    lifecycle = with_stub_gh("ok")
    assert lifecycle._fetch_issue(1) == {
        "number": 1, "title": "t", "state": "OPEN", "labels": [], "body": "b",
    }
    assert lifecycle._last_fetch_verdict is None


def test_a_missing_issue_is_recorded_as_an_answer(with_stub_gh) -> None:
    lifecycle = with_stub_gh("not_found")
    assert lifecycle._fetch_issue(99999999) is None
    assert lifecycle._last_fetch_verdict.established


def test_a_rate_limit_is_recorded_as_no_answer(with_stub_gh) -> None:
    """THE DEFECT: this used to be indistinguishable from the case above."""
    lifecycle = with_stub_gh("rate_limit")
    assert lifecycle._fetch_issue(1876) is None
    assert not lifecycle._last_fetch_verdict.established
    assert lifecycle._last_fetch_verdict.kind == gh_failure.UNAVAILABLE


def test_the_two_failures_do_not_print_the_same_sentence(with_stub_gh) -> None:
    absent = with_stub_gh("not_found")
    absent._fetch_issue(99999999)
    absent_msg = absent._explain_fetch_failure(99999999, "for the transition gate")

    unavailable = with_stub_gh("rate_limit")
    unavailable._fetch_issue(1876)
    unavailable_msg = unavailable._explain_fetch_failure(1876, "for the transition gate")

    assert absent_msg != unavailable_msg
    assert "does not exist" in absent_msg
    assert "does not exist" not in unavailable_msg, (
        "a rate-limited call is still being reported as a missing issue"
    )


def test_a_transport_failure_names_the_transport(with_stub_gh) -> None:
    lifecycle = with_stub_gh("network")
    lifecycle._fetch_issue(1876)
    assert "unreachable" in lifecycle._explain_fetch_failure(1876)


def test_unparseable_output_is_not_reported_as_a_missing_issue(with_stub_gh) -> None:
    """`gh` exits 0 here, so the old ValueError path swallowed it into the same
    None as everything else."""
    lifecycle = with_stub_gh("garbage")
    assert lifecycle._fetch_issue(1) is None
    assert lifecycle._last_fetch_verdict.kind == gh_failure.MALFORMED
    assert "does not exist" not in lifecycle._explain_fetch_failure(1)


def test_a_missing_gh_binary_is_unavailable_not_absent(monkeypatch, tmp_path) -> None:
    """Nothing was asked, so nothing is known about the issue."""
    monkeypatch.setenv("PATH", str(tmp_path))
    lifecycle = IssueLifecycle()
    assert lifecycle._fetch_issue(1876) is None
    assert not lifecycle._last_fetch_verdict.established
    assert "not installed" in lifecycle._last_fetch_verdict.detail
