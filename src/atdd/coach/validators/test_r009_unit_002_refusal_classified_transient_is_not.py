# URN: test:govern-lifecycle:R009-UNIT-002-a-refusal-is-classified-and-a-transient-fault-is-not
# Acceptance: acc:govern-lifecycle:R009-UNIT-002-a-refusal-is-classified-and-a-transient-fault-is-not
# WMBT: wmbt:govern-lifecycle:R009
# Phase: RED
# Layer: backend.integration
# Assertion: behavioral
"""R009-UNIT-002 — a refusal is classified and names the credential; a transient
fault, including the 403s GitHub uses for rate limiting, is never reclassified.

The boundary runs in both directions and both directions matter.

Forwards: GitHub's "authenticated, but not authorised" wording must arrive as a
distinct type. When it arrived as a plain ``GitHubClientError`` — the same shape
as any transport failure — two separate investigations of #1601 read it as
GitHub flakiness and never looked at the token (#1621).

Backwards, and just as important: GitHub answers a secondary rate limit with
**HTTP 403**, the same status as a refusal. Classifying on the status code
rather than the wording tells an operator who need only wait that their token
lacks a scope — the identical misdiagnosis pointed the other way, and the reason
this file matches phrases and never the code.
"""
from __future__ import annotations

import subprocess

import pytest

from atdd.coach.github import (
    GitHubClient,
    GitHubClientError,
    GitHubPermissionError,
)

# The exact stderr from run 30199788383 on #1601.
_LIVE_REFUSAL = (
    "GraphQL: Resource not accessible by personal access token "
    "(removeLabelsFromLabelable)"
)


def _run_gh_returning(monkeypatch, returncode: int, stderr: str) -> GitHubClient:
    """A GitHubClient whose every `gh` invocation fails with ``stderr``."""
    monkeypatch.setattr(GitHubClient, "_check_gh", lambda self: None)
    client = GitHubClient(repo="afokapu/atdd")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, returncode, stdout="", stderr=stderr)

    monkeypatch.setattr("atdd.coach.github.subprocess.run", fake_run)
    return client


# ---------------------------------------------------------------------------
# Forwards: a refusal is a refusal
# ---------------------------------------------------------------------------

def test_permission_refusal_is_raised_as_its_own_type(monkeypatch) -> None:
    """The refusal is distinguishable in code, not just in prose."""
    client = _run_gh_returning(monkeypatch, 1, _LIVE_REFUSAL)

    with pytest.raises(GitHubPermissionError) as refused:
        client.remove_label(1601, ["atdd:REFACTOR"])

    # Still a GitHubClientError, so existing handlers keep working.
    assert isinstance(refused.value, GitHubClientError)
    message = str(refused.value)
    assert "permission" in message.lower(), message
    # It names the failing call and quotes what GitHub actually said.
    assert "issue" in message and "edit" in message, message
    assert "Resource not accessible" in message, message


def test_permission_refusal_names_the_credential_in_play(monkeypatch) -> None:
    """"Which token?" is the first question, so the error answers it."""
    monkeypatch.setenv("GH_TOKEN", "ghp_whatever")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    client = _run_gh_returning(monkeypatch, 1, _LIVE_REFUSAL)

    with pytest.raises(GitHubPermissionError) as refused:
        client.add_label(1601, ["atdd:COMPLETE"])
    assert "GH_TOKEN" in str(refused.value), str(refused.value)


@pytest.mark.parametrize(
    "stderr",
    [
        _LIVE_REFUSAL,
        "GraphQL: Resource not accessible by integration (addLabelsToLabelable)",
        "HTTP 403: Resource not accessible by integration",
    ],
)
def test_both_token_flavours_of_refusal_are_recognised(monkeypatch, stderr) -> None:
    """GitHub words it differently for a PAT and for GITHUB_TOKEN; both mean the same.

    The third case carries ``HTTP 403`` and is still recognised — by the phrase,
    not the code. That is the distinction the transient cases below depend on.
    """
    client = _run_gh_returning(monkeypatch, 1, stderr)
    with pytest.raises(GitHubPermissionError):
        client.add_label(1601, ["atdd:COMPLETE"])


# ---------------------------------------------------------------------------
# Backwards: a transient fault is not a refusal
# ---------------------------------------------------------------------------

#: Failures that are NOT refusals. Each would be actively harmed by the
#: permission diagnosis, which tells the reader that retrying cannot help.
_TRANSIENT_FAILURES = [
    pytest.param(
        "error connecting to api.github.com: i/o timeout",
        id="transport-timeout",
    ),
    # GitHub answers a secondary rate limit with 403 — the SAME status as a
    # refusal. Classifying on the status code rather than the wording is how a
    # rate limit gets reported as a missing scope: an operator who need only
    # wait is sent to audit token scopes instead.
    pytest.param(
        "HTTP 403: You have exceeded a secondary rate limit and have been "
        "temporarily blocked from content creation. Please retry your request "
        "again later. (https://api.github.com/repos/afokapu/atdd/issues/1601/labels)",
        id="secondary-rate-limit-403",
    ),
    pytest.param(
        "HTTP 403: API rate limit exceeded for user ID 1. "
        "(https://api.github.com/repos/afokapu/atdd/issues/1601/labels)",
        id="primary-rate-limit-403",
    ),
]


@pytest.mark.parametrize("stderr", _TRANSIENT_FAILURES)
def test_an_ordinary_failure_is_not_reclassified(monkeypatch, stderr) -> None:
    """Only a refusal is a refusal — a transient fault stays a plain error."""
    client = _run_gh_returning(monkeypatch, 1, stderr)

    with pytest.raises(GitHubClientError) as failed:
        client.add_label(1601, ["atdd:COMPLETE"])
    assert not isinstance(failed.value, GitHubPermissionError), (
        f"a transient failure ({stderr[:60]}...) was reported as a permission "
        "problem. The two have opposite remedies — one is waited out, the other "
        "is never fixed by waiting — and must not be conflated."
    )
    assert "retrying cannot help" not in str(failed.value), (
        "a retryable failure was told that retrying cannot help"
    )
