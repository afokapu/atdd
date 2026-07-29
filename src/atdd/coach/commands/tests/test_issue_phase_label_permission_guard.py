"""A label write refused for lack of permission must say so (#1621).

The token bug is one line of YAML. The reason it survived two full investigations
is this: when the write failed, it failed as an unhandled ``GitHubClientError``
carrying only ``gh command failed: issue edit ... --remove-label atdd:REFACTOR``
and a GraphQL string. That shape is indistinguishable from a network blip, so
twice it was read as GitHub flakiness and twice nobody looked at the token.

A permission refusal is not a transient fault and must never present as one:
no retry fixes a scope that was never granted. It also leaves real damage —
the store write lands first (#1452), so a refused label write means
``objects.state`` has advanced and the ``atdd:<phase>`` label has not. The
operator has to be told that, not handed a traceback.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, List

import pytest

from atdd.coach.commands.issue import IssueManager
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


class _RefusingClient:
    """A client whose label writes are refused for lack of permission."""

    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls: List[str] = []

    def remove_label(self, issue_number: int, labels: List[str]) -> None:
        self.calls.append("remove")
        raise self.error

    def add_label(self, issue_number: int, labels: List[str]) -> None:
        self.calls.append("add")
        raise self.error


class _WorkingClient:
    def __init__(self) -> None:
        self.calls: List[Any] = []

    def remove_label(self, issue_number: int, labels: List[str]) -> None:
        self.calls.append(("remove", labels))

    def add_label(self, issue_number: int, labels: List[str]) -> None:
        self.calls.append(("add", labels))


def _run_gh_returning(monkeypatch, returncode: int, stderr: str) -> GitHubClient:
    """A GitHubClient whose every `gh` invocation fails with ``stderr``."""
    monkeypatch.setattr(GitHubClient, "_check_gh", lambda self: None)
    client = GitHubClient(repo="afokapu/atdd")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, returncode, stdout="", stderr=stderr)

    monkeypatch.setattr("atdd.coach.github.subprocess.run", fake_run)
    return client


# ---------------------------------------------------------------------------
# _run_gh classifies the refusal
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


#: Failures that are NOT refusals. Each would be actively harmed by the
#: permission diagnosis, which tells the reader that retrying cannot help.
_TRANSIENT_FAILURES = [
    pytest.param(
        "error connecting to api.github.com: i/o timeout",
        id="transport-timeout",
    ),
    # GitHub answers a secondary rate limit with 403 — the SAME status as a
    # refusal. Classifying on the status code rather than the wording is how a
    # rate limit gets reported as a missing scope, which is the original defect
    # pointed the other way: an operator who need only wait is sent to audit
    # token scopes instead.
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


@pytest.mark.parametrize(
    "stderr",
    [
        _LIVE_REFUSAL,
        "GraphQL: Resource not accessible by integration (addLabelsToLabelable)",
        "HTTP 403: Resource not accessible by integration",
    ],
)
def test_both_token_flavours_of_refusal_are_recognised(monkeypatch, stderr) -> None:
    """GitHub words it differently for a PAT and for GITHUB_TOKEN; both mean the same."""
    client = _run_gh_returning(monkeypatch, 1, stderr)
    with pytest.raises(GitHubPermissionError):
        client.add_label(1601, ["atdd:COMPLETE"])


# ---------------------------------------------------------------------------
# _write_phase_label reports instead of exploding
# ---------------------------------------------------------------------------

def test_refused_label_write_reports_and_does_not_raise(capsys) -> None:
    """The operator gets a diagnosis and a non-success return, not a traceback."""
    client = _RefusingClient(
        GitHubPermissionError(
            f"gh command refused for lack of permission: issue edit 1601\n{_LIVE_REFUSAL}"
        )
    )

    written = IssueManager._write_phase_label(
        client, 1601, ["atdd-issue", "atdd:REFACTOR"], "COMPLETE"
    )

    assert written is False, "a refused label write must not report success"
    out = capsys.readouterr().out
    assert "atdd:COMPLETE" in out, out
    assert "1601" in out, out
    # It must name the cause as permission, not leave the reader guessing.
    assert "permission" in out.lower(), out
    # And it must name the damage: the store already moved (#1452).
    assert "objects.state" in out or "store" in out.lower(), out


def test_a_successful_label_write_still_reports_success() -> None:
    """The guard must not turn every write into a failure."""
    client = _WorkingClient()
    written = IssueManager._write_phase_label(
        client, 1601, ["atdd-issue", "atdd:REFACTOR"], "COMPLETE"
    )
    assert written is True
    assert ("remove", ["atdd:REFACTOR"]) in client.calls
    assert ("add", ["atdd:COMPLETE"]) in client.calls


def test_a_non_permission_failure_still_propagates() -> None:
    """The guard catches a refusal, not everything.

    Swallowing an unexpected error here would recreate the original defect in a
    politer form: a transition reported as fine when the label never moved.
    """
    client = _RefusingClient(GitHubClientError("gh command failed: i/o timeout"))
    with pytest.raises(GitHubClientError):
        IssueManager._write_phase_label(
            client, 1601, ["atdd-issue", "atdd:REFACTOR"], "COMPLETE"
        )


def test_update_returns_nonzero_when_the_label_write_is_refused(monkeypatch) -> None:
    """`atdd coach transition` must exit red, so CI cannot read it as done."""
    manager = IssueManager(target_dir=Path("."))
    refusing = _RefusingClient(GitHubPermissionError(f"refused\n{_LIVE_REFUSAL}"))

    monkeypatch.setattr(manager, "_check_initialized", lambda: True)
    monkeypatch.setattr(
        manager,
        "_resolve_issue",
        lambda issue_id: (1601, {"labels": [{"name": "atdd:REFACTOR"}], "body": ""}, refusing),
    )
    monkeypatch.setattr(manager, "_read_phase_labels", lambda issue: (["atdd:REFACTOR"], "REFACTOR"))
    monkeypatch.setattr(
        manager, "_transition_gates_pass", lambda *a, **k: True
    )
    monkeypatch.setattr(manager, "_update_manifest_status", lambda n, s: None)

    assert manager.update("1601", status="COMPLETE") == 1


# ---------------------------------------------------------------------------
# The repair path must not report a projection it did not make
# ---------------------------------------------------------------------------

def test_reprojection_reports_nothing_projected_when_the_write_is_refused(
    monkeypatch,
) -> None:
    """The repair verb cannot claim to have closed the drift it was called to close.

    ``reproject_phase_label`` exists to make a drifted label agree with the
    store again (#1338). If its one write is refused and it still returns the
    phase, the caller prints "label re-projected from the store := COMPLETE"
    over a label that never moved — manufacturing exactly the store/label
    disagreement the verb repairs, and reporting it as repaired.
    """
    manager = IssueManager(target_dir=Path("."))
    refusing = _RefusingClient(GitHubPermissionError(f"refused\n{_LIVE_REFUSAL}"))

    monkeypatch.setattr(
        "atdd.coach.commands.auto_phase.read_store_phase",
        lambda n, d: "COMPLETE",
    )
    monkeypatch.setattr(
        manager,
        "_resolve_issue",
        lambda issue_id: (1601, {"labels": [{"name": "atdd:REFACTOR"}]}, refusing),
    )

    assert manager.reproject_phase_label(1601) is None, (
        "a refused re-projection reported the phase as projected"
    )


def test_reprojection_still_reports_the_phase_when_the_write_lands(monkeypatch) -> None:
    """The guard must not turn every repair into a failure."""
    manager = IssueManager(target_dir=Path("."))
    working = _WorkingClient()

    monkeypatch.setattr(
        "atdd.coach.commands.auto_phase.read_store_phase",
        lambda n, d: "COMPLETE",
    )
    monkeypatch.setattr(
        manager,
        "_resolve_issue",
        lambda issue_id: (1601, {"labels": [{"name": "atdd:REFACTOR"}]}, working),
    )

    assert manager.reproject_phase_label(1601) == "COMPLETE"
    assert ("add", ["atdd:COMPLETE"]) in working.calls
