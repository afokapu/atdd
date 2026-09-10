# URN: test:govern-lifecycle:issue-fetch-separates-absent-from-unavailable:E074-UNIT-001-absent-is-not-unavailable
# Acceptance: acc:govern-lifecycle:E074-UNIT-001-absent-is-not-unavailable
# WMBT: wmbt:govern-lifecycle:E074
# Phase: GREEN
# Layer: backend.unit
"""E074-UNIT-001 — "no such issue" and "GitHub would not answer" are different
outcomes and must not print the same sentence (#1895).

`gh issue view` exits 1 for both. The caller collapsed them into None and printed
"could not fetch issue #N", so a rate limit read as a missing issue and sent the
operator looking for an issue that was open and fine.

Only ABSENT is an answer. Every other outcome is the absence of one, and an
outcome this module does not recognise must land on UNAVAILABLE — guessing
"absent" from an unfamiliar message would reintroduce the conflation silently.
"""
from __future__ import annotations

import pytest

from atdd.coach.utils import gh_failure

# Captured from real failures against this repository, not composed.
REAL_ABSENT = "GraphQL: Could not resolve to an issue or pull request with the number of 99999999. (repository.issue)"
REAL_RATE_LIMIT = "GraphQL: API rate limit already exceeded for user ID 8843832."


def test_a_missing_issue_is_an_answer() -> None:
    verdict = gh_failure.classify(REAL_ABSENT)
    assert verdict.kind == gh_failure.ABSENT
    assert verdict.established, "the API answered: the issue is not there"


def test_a_rate_limit_is_not_an_answer() -> None:
    """THE DEFECT. This is the message that read as a missing issue."""
    verdict = gh_failure.classify(REAL_RATE_LIMIT)
    assert verdict.kind == gh_failure.UNAVAILABLE
    assert not verdict.established


@pytest.mark.parametrize("stderr", [
    "You have exceeded a secondary rate limit. Please wait a few minutes.",
    "gh: set the GH_TOKEN environment variable.",
    "gh: authentication failed for host github.com",
    "error connecting to api.github.com: dial tcp: lookup api.github.com: no such host",
    "connection refused",
    "GraphQL: Something went wrong while executing your query. (502)",
])
def test_every_transport_failure_is_unavailable(stderr: str) -> None:
    assert not gh_failure.classify(stderr).established


def test_an_unrecognised_failure_is_unavailable_not_absent() -> None:
    """The load-bearing default. A message nobody has classified says nothing
    about whether the issue exists, and must not be read as saying it does not."""
    verdict = gh_failure.classify("some entirely new failure mode from a future gh")
    assert verdict.kind == gh_failure.UNAVAILABLE
    assert not verdict.established


def test_malformed_output_is_neither_absent_nor_a_transport_failure() -> None:
    """`gh` exited 0, so retrying will not help, and nothing said the issue is
    missing."""
    verdict = gh_failure.malformed("not json at all")
    assert verdict.kind == gh_failure.MALFORMED
    assert not verdict.established


def test_only_the_absent_verdict_may_say_the_issue_does_not_exist() -> None:
    """The rendered sentence is the whole point of the fix."""
    absent = gh_failure.render(1876, gh_failure.classify(REAL_ABSENT))
    unavailable = gh_failure.render(1876, gh_failure.classify(REAL_RATE_LIMIT))

    assert "does not exist" in absent
    assert "does not exist" not in unavailable, (
        "an unavailable API is being reported as a missing issue — the defect"
    )
    assert "could not be read" in unavailable


def test_the_rendered_remedy_is_actionable_per_cause() -> None:
    rate = gh_failure.render(1876, gh_failure.classify(REAL_RATE_LIMIT))
    assert "rate_limit" in rate, "the remedy should name the command that shows the reset"
    assert "separate" in rate, (
        "REST and GraphQL have separate buckets; a reader who checks the wrong one "
        "sees a full quota and concludes the diagnosis is wrong"
    )


def test_context_rides_on_the_cause_line_not_after_the_remedy() -> None:
    rendered = gh_failure.render(1876, gh_failure.classify(REAL_RATE_LIMIT),
                                 "for the transition gate")
    first_line = rendered.splitlines()[0]
    assert "for the transition gate" in first_line
