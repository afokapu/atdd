# URN: test:govern-lifecycle:coach-operator-safety-invariants:REST-UNIT-001-lifecycle-path-makes-no-graphql-call
# Phase: RED
# Layer: unit
# Assertion: behavioral
# Runtime: python
"""REST-UNIT-001 — reading and labelling an issue never touches GraphQL (#1989).

`gh issue view/edit` and `gh api graphql` share one bucket, and it is the bucket
that runs out. Measured 2026-09-13: GraphQL refused every call with "rate limit
already exceeded" while REST reported 4644/5000 remaining. The damage was not
confined to the call that failed —

  * a phase transition could not read its own issue, so the whole ladder stalled;
  * `validate-coach` reported TWELVE validators as COULD_NOT_CHECK, because the
    prefetch marked all five of its keys with whichever exception it caught, and
    only the sub-issue query was actually GraphQL-backed.

So the pin is on the TRANSPORT, not on the symptom: if any of these paths grows a
GraphQL call again, the rate limit stops being the thing that tells us.
"""
from __future__ import annotations

import pytest

from atdd.coach.github import GitHubClient

pytestmark = [pytest.mark.coach]

#: argv shapes that resolve to POST /graphql, whatever they look like.
_GRAPHQL = (("api", "graphql"), ("issue", "view"), ("issue", "edit"),
            ("issue", "list"), ("pr", "view"), ("pr", "list"))


def _assert_rest(argv: list) -> None:
    head = tuple(a for a in argv[:2])
    assert head not in _GRAPHQL, f"GraphQL-backed argv on a lifecycle path: {argv}"
    assert argv[0] == "api", f"expected a `gh api` call, got: {argv}"


class _Spy(GitHubClient):
    """A client that records argv instead of shelling `gh`."""

    def __init__(self, repo: str = "o/r") -> None:  # noqa: D107 - no gh probing
        self.repo = repo
        self.calls: list = []

    def _run_gh(self, args, **_kw):
        self.calls.append(list(args))
        _assert_rest(list(args))
        return "{}"


def test_reading_an_issue_uses_rest() -> None:
    spy = _Spy()
    spy.get_issue(1989)

    assert spy.calls, "get_issue asked nothing"
    assert spy.calls[0][1] == "repos/o/r/issues/1989"


def test_adding_a_label_uses_rest() -> None:
    spy = _Spy()
    spy.add_label(1989, ["atdd:GREEN"])

    assert spy.calls[0][1] == "repos/o/r/issues/1989/labels"
    assert "labels[]=atdd:GREEN" in spy.calls[0]


def test_removing_a_label_uses_rest_and_one_delete_per_label() -> None:
    spy = _Spy()
    spy.remove_label(1989, ["atdd:RED", "atdd:SMOKE"])

    assert len(spy.calls) == 2, "REST has no batch label delete; one call each"
    for call in spy.calls:
        assert "--method" in call and "DELETE" in call


def test_issue_state_is_normalised_to_the_vocabulary_callers_compare_against() -> None:
    """REST says "open", every caller compares against "OPEN"."""
    class _Open(_Spy):
        def _run_gh(self, args, **_kw):
            super()._run_gh(args)
            return '{"number": 1, "state": "open"}'

    assert _Open().get_issue(1)["state"] == "OPEN"
