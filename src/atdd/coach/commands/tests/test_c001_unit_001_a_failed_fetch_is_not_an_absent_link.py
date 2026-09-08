# URN: test:drive-state-machine:post-merge-advance-is-observable:C001-UNIT-001-a-failed-fetch-is-not-an-absent-link
# Acceptance: acc:drive-state-machine:C001-UNIT-001-a-failed-fetch-is-not-an-absent-link
# WMBT: wmbt:drive-state-machine:C001
# Phase: RED
# Layer: application
"""C001-UNIT-001 — "I could not look" is not "there is nothing there".

`_fetch_pr` returns None on a non-zero `gh` exit and on TimeoutExpired,
FileNotFoundError or ValueError alike, so `resolve_linked_issue` reports an
absent link for a PR whose link is fine. Observed on PR #1806, whose
closingIssuesReferences is [1708].

Speaks the vocabulary #1747/#1748 already built in
`atdd.coach.validators._observation` rather than inventing a second one.
"""
from __future__ import annotations

import pytest

from atdd.coach.commands.pr import PRManager
from atdd.coach.validators._observation import Observation


def _mgr(monkeypatch, pr_payload, fetch_ok=True):
    mgr = PRManager()
    if fetch_ok:
        monkeypatch.setattr(mgr, "_fetch_pr", lambda n: pr_payload)
    else:
        monkeypatch.setattr(mgr, "_fetch_pr", lambda n: None)
    return mgr


def test_a_failed_fetch_reads_as_unreadable(monkeypatch):
    mgr = _mgr(monkeypatch, None, fetch_ok=False)

    reading = mgr.read_linked_issue(1806)

    assert reading.observation is Observation.UNREADABLE, (
        "the PR could not be fetched; reporting 'no linked issue' states a fact "
        f"about the repository that was never observed. got {reading.observation}"
    )
    assert reading.reason, "a refusal an operator cannot act on is barely better than a vacuous pass"


def test_a_pr_with_no_link_reads_as_no_obligation(monkeypatch):
    """Held precisely: a PR that genuinely closes nothing owes this nothing.

    Every strategy is stubbed to find nothing rather than hand-crafting a payload
    that happens to match none of them — the first attempt did the latter and
    strategy 4 resolved a real issue over the network, which is neither hermetic
    nor what this acceptance is about.
    """
    mgr = _mgr(monkeypatch, {"number": 42, "body": "", "title": "",
                             "headRefName": "x", "closingIssuesReferences": []})
    for name in ("_resolve_via_api", "_resolve_via_body",
                 "_resolve_via_manifest", "_resolve_via_title"):
        monkeypatch.setattr(mgr, name, lambda _pr: None)

    reading = mgr.read_linked_issue(42)

    assert reading.observation is Observation.NO_OBLIGATION, (
        f"nothing to read is not a failure to read; got {reading.observation}"
    )


def test_a_linked_pr_reads_as_observed(monkeypatch):
    mgr = _mgr(monkeypatch, {"number": 1806, "body": "Closes #1708", "title": "t",
                             "headRefName": "x",
                             "closingIssuesReferences": [{"number": 1708}]})
    monkeypatch.setattr(mgr, "_fetch_issue", lambda n: {"number": n, "labels": []})

    reading = mgr.read_linked_issue(1806)

    assert reading.observation is Observation.OBSERVED
    assert reading.payload and reading.payload.get("issue_number") == 1708
