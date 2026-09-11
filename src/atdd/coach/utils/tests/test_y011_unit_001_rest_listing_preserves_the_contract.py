# URN: test:govern-lifecycle:issue-listing-uses-rest:Y011-UNIT-001-rest-listing-preserves-the-contract
# Acceptance: acc:govern-lifecycle:Y011-UNIT-001-rest-listing-preserves-the-contract
# WMBT: wmbt:govern-lifecycle:Y011
# Phase: GREEN
# Layer: backend.unit
"""Y011-UNIT-001 — moving the listing to REST must change nothing callers can see (#1930).

`gh issue list --json` is `POST /graphql`, so the whole coach validator surface
sat on the one bucket that keeps failing in CI. The fix is a transport change and
nothing more: every caller must get back exactly what it got before.

Two differences make that non-trivial, and both are silent if unchecked.

* REST's `/issues` **includes pull requests**. Measured on this repository: the
  unlabelled listing returns 319 over REST and 296 over GraphQL — 23 PRs. The
  count goes UP, so a naive swap looks healthy while every validator's subject
  quietly grows.
* REST reports `state` as `"open"`, gh reports `"OPEN"`. Callers compare against
  both cases in different places, so the listing keeps gh's form. Changing the
  transport is the job; changing the contract is not.
"""
from __future__ import annotations

import pytest

from atdd.coach.github import normalise_rest_issues


def _issue(number: int, **over):
    base = {
        "number": number,
        "title": f"issue {number}",
        "state": "open",
        "labels": [{"name": "atdd-issue"}, {"name": "atdd:INIT"}],
        "body": "body text",
    }
    base.update(over)
    return base


def _pull(number: int):
    return {**_issue(number), "pull_request": {"url": "https://api.github.com/..."}}


def test_pull_requests_are_dropped() -> None:
    """THE TRAP: REST /issues returns PRs too, and the count going up hides it."""
    rows = normalise_rest_issues([_issue(1), _pull(2), _issue(3)], fields="number,title,labels,state")
    assert [r["number"] for r in rows] == [1, 3]


def test_state_keeps_the_shape_callers_already_read() -> None:
    """gh says OPEN, REST says open. The contract is gh's."""
    rows = normalise_rest_issues([_issue(1, state="open"), _issue(2, state="closed")],
                                 fields="number,title,labels,state")
    assert [r["state"] for r in rows] == ["OPEN", "CLOSED"]


def test_labels_keep_their_object_shape() -> None:
    """Callers read `l["name"]`, not a bare string."""
    rows = normalise_rest_issues([_issue(1)], fields="number,title,labels,state")
    assert rows[0]["labels"] == [{"name": "atdd-issue"}, {"name": "atdd:INIT"}]


def test_body_is_included_only_when_asked_for() -> None:
    """`include_body=False` callers must not start receiving bodies — that is a
    large payload several validators neither want nor read."""
    without = normalise_rest_issues([_issue(1)], fields="number,title,labels,state")
    assert "body" not in without[0]
    with_body = normalise_rest_issues([_issue(1)], fields="number,title,labels,state,body")
    assert with_body[0]["body"] == "body text"


def test_a_missing_body_becomes_empty_string_not_none() -> None:
    """REST returns null for an empty body; gh returns "". Callers do string work."""
    rows = normalise_rest_issues([_issue(1, body=None)], fields="number,title,labels,state,body")
    assert rows[0]["body"] == ""


def test_only_the_requested_fields_come_back() -> None:
    """REST returns ~30 keys per issue. Passing them through would change what
    every caller sees and make the payload far larger than the gh one."""
    rows = normalise_rest_issues(
        [{**_issue(1), "assignee": None, "milestone": None, "url": "..."}],
        fields="number,title,labels,state",
    )
    assert set(rows[0]) == {"number", "title", "labels", "state"}


@pytest.mark.parametrize("rows", [[], None])
def test_an_empty_answer_is_an_empty_list(rows) -> None:
    assert normalise_rest_issues(rows or [], fields="number,title,labels,state") == []
