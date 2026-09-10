# URN: test:govern-lifecycle:validator-fixtures-refuse-when-unestablished:E075-UNIT-001-an-unreachable-api-is-not-a-pass
# Acceptance: acc:govern-lifecycle:E075-UNIT-001-an-unreachable-api-is-not-a-pass
# WMBT: wmbt:govern-lifecycle:E075
# Phase: GREEN
# Layer: backend.unit
"""E075-UNIT-001 — a validator that could not query GitHub refuses instead of
reporting green (#1896).

Six fixtures called `pytest.skip` when the API threw. A skipped test is GREEN, so
16 test functions across 8 validator files reported nothing whenever GitHub was
unreachable — and in a CI summary "reported nothing" is indistinguishable from
"found nothing wrong".

#1892 is the proof: validate-coach passed on one PR and failed on the next with
the same code and the same 14 pre-existing unlabeled issues. The difference was
API availability.

The fixtures are driven directly through `__wrapped__`, because what is under test
is the fixture's own decision, not any validator that consumes it.
"""
from __future__ import annotations

import pytest

from atdd.coach.validators import conftest as vconf

_API_ERROR = RuntimeError("GraphQL: API rate limit already exceeded for user ID 8843832.")

_QUERY_FIXTURES = [
    ("github_issues", "issues"),
    ("github_complete_issues", "complete_issues"),
    ("all_open_issues_unfiltered", "all_open_issues"),
    ("github_sub_issues", "sub_issues"),
    ("github_closed_sub_issues", "closed_sub_issues"),
]


def _undecorated(fixture: object):
    """The plain function pytest wrapped in a fixture.

    pytest stores it on `__wrapped__`, but the declared type
    (`FixtureFunctionDefinition`) does not carry the attribute, so pyright
    objects to the direct access and ruff B009 objects to `getattr` with a
    constant name. Working around one linter walks into the other, so this is one
    justified ignore in one place, saying what is actually going on.
    """
    return fixture.__wrapped__  # type: ignore[attr-defined]


def _call(fixture_name: str, prefetch: dict):
    return _undecorated(getattr(vconf, fixture_name))(prefetch)


# `pytest.fail` raises Failed, which subclasses BaseException rather than
# Exception — so `pytest.raises(Exception)` does NOT catch it and a test written
# that way reports the refusal as an error instead of asserting on it.



def _refusal(fixture_name: str, prefetch: dict) -> str:
    """Drive a fixture that must REFUSE, and return the refusal message.

    Deliberately not `pytest.raises`. A `Skipped` exception is not caught by
    `pytest.raises(pytest.fail.Exception)` — it propagates, and pytest then marks
    THIS test skipped, which every runner reports as green. Written that way, a
    guard against "a skip is green" is itself greened by the skip it exists to
    catch. Measured: reintroducing the defect turned this file into
    "11 passed, 4 skipped" with no failure at all.

    So the skip is caught first and converted into a failure.
    """
    try:
        _call(fixture_name, prefetch)
    except pytest.skip.Exception as exc:
        pytest.fail(
            f"{fixture_name} SKIPPED on an unestablished verdict: {exc}\n"
            "A skipped test is reported green. That is the defect."
        )
    except pytest.fail.Exception as exc:
        return str(exc)
    pytest.fail(f"{fixture_name} returned normally instead of refusing")


@pytest.mark.parametrize("fixture_name,key", _QUERY_FIXTURES)
def test_a_failed_query_refuses(fixture_name: str, key: str) -> None:
    """THE DEFECT: every one of these used to skip, and a skip is green."""
    assert "COULD_NOT_CHECK" in _refusal(fixture_name, {key: _API_ERROR})


@pytest.mark.parametrize("fixture_name,key", _QUERY_FIXTURES)
def test_the_refusal_is_not_a_skip(fixture_name: str, key: str) -> None:
    """A skip would be reported green by every runner and every CI summary."""
    message = _refusal(fixture_name, {key: _API_ERROR})
    assert "not a pass" in message


def test_the_refusal_names_the_cause_and_what_to_do() -> None:
    message = _refusal("github_issues", {"issues": _API_ERROR})
    assert "rate limit" in message, "the underlying cause is not surfaced"
    assert "not a pass" in message
    assert "not github_api" in message, (
        "the operator is not told how to deselect these deliberately, which is "
        "the difference between an unevaluated suite and a green one"
    )


def test_an_absent_prefetch_key_is_not_an_empty_answer() -> None:
    """`None` means the query never ran; `[]` would mean the repository really has
    none. Treating the first as the second is the same conflation one level down."""
    assert "never ran" in _refusal("all_open_issues_unfiltered", {"all_open_issues": None})


def test_an_empty_result_still_skips() -> None:
    """A query that SUCCEEDED and found nothing is an answer, and the validator
    genuinely has nothing to check. This must stay a skip, or the fix becomes a
    different false alarm."""
    with pytest.raises(pytest.skip.Exception):
        _call("github_issues", {"issues": []})


def test_degraded_branch_protection_refuses() -> None:
    """The highest-stakes instance: "is main protected?" answered GREEN whenever
    the answer was unknown."""
    from atdd.coach.commands.branch_protection import ProtectionStatus

    message = _refusal(
        "protection_result",
        {"branch_protection": (ProtectionStatus.DEGRADED, ["token lacks admin scope"])},
    )
    assert "COULD_NOT_CHECK" in message
    assert "token lacks admin scope" in message


def test_an_unconfigured_repository_still_skips() -> None:
    """NOT_APPLICABLE, not COULD_NOT_CHECK: a repo with no GitHub integration is
    not owed these validators at all."""
    import inspect

    source = inspect.getsource(_undecorated(vconf.github_client))
    assert "pytest.skip" in source and "not configured" in source
