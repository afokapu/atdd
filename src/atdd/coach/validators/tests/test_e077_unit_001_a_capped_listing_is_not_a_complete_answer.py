# URN: test:govern-lifecycle:issue-fetches-refuse-to-truncate:E077-UNIT-001-a-capped-listing-is-not-a-complete-answer
# Acceptance: acc:govern-lifecycle:E077-UNIT-001-a-capped-listing-is-not-a-complete-answer
# WMBT: wmbt:govern-lifecycle:E077
# Phase: GREEN
# Layer: backend.unit
"""E077-UNIT-001 — a listing that hit its cap is not a complete answer (#1903).

`list_issues_by_label` passed `--limit 100` with no pagination. `gh` returns 100
rows and says nothing about the rest, so every validator behind the prefetch
reported PASS over a SAMPLE. Measured on this repository: 100 of 289 open
atdd-issues, and the 100 were the NEWEST — so ten issues labelled minutes earlier
sat outside the window and the label validator passed without ever seeing them.

At exactly N rows, "there were N" and "there were more" are the same observation.
So the cap raises rather than returning a prefix: completeness is unknown, and
unknown is not clean.

`get_sub_issues`, ten lines below in the same class, has always used
`--paginate`. Both return a plain list, and nothing at either call site marks one
as an answer and the other as a sample — which is what made this invisible.
"""
from __future__ import annotations

import json

import pytest

from atdd.coach.github import GitHubClient, GitHubResultTruncated


class _StubClient(GitHubClient):
    """A client whose gh invocation is replaced by a fixed row count."""

    def __init__(self, rows: int) -> None:
        self._rows = rows
        self.repo = "owner/repo"
        self.calls: list[list[str]] = []

    def _run_gh(self, args, input_text=None):  # type: ignore[override]
        self.calls.append(args)
        return json.dumps([{"number": i, "labels": []} for i in range(self._rows)])


def test_a_short_listing_is_returned_whole() -> None:
    client = _StubClient(rows=42)
    assert len(client.list_issues_by_label("atdd-issue")) == 42


def test_a_listing_at_the_cap_refuses() -> None:
    """THE DEFECT. This used to return the prefix and say nothing."""
    client = _StubClient(rows=GitHubClient._ISSUE_FETCH_CAP)
    with pytest.raises(GitHubResultTruncated) as excinfo:
        client.list_issues_by_label("atdd-issue")
    assert "UNKNOWN" in str(excinfo.value)


def test_the_refusal_names_what_was_asked_for() -> None:
    client = _StubClient(rows=GitHubClient._ISSUE_FETCH_CAP)
    with pytest.raises(GitHubResultTruncated) as excinfo:
        client.list_issues_by_label("atdd:COMPLETE")
    assert "atdd:COMPLETE" in str(excinfo.value)


def test_the_unfiltered_listing_refuses_at_the_cap_too() -> None:
    """`list_all_open_issues` carried a 500 cap — latent at today's volume, the
    same defect waiting."""
    client = _StubClient(rows=GitHubClient._ISSUE_FETCH_CAP)
    with pytest.raises(GitHubResultTruncated):
        client.list_all_open_issues()


def test_no_prefetch_fetch_carries_a_hardcoded_row_limit() -> None:
    """The regression guard. A number typed into a fetch is a silent sample."""
    import inspect

    source = inspect.getsource(GitHubClient)
    for method in ("list_issues_by_label", "list_all_open_issues"):
        body = source.split(f"def {method}(", 1)[1].split("\n    def ", 1)[0]
        assert '"--limit"' not in body, (
            f"{method} passes a literal --limit again; it will return a prefix "
            "that every caller reads as the whole answer."
        )


def test_the_cap_is_far_above_any_plausible_repository() -> None:
    """A cap that a real repository can reach is a truncation with extra steps."""
    assert GitHubClient._ISSUE_FETCH_CAP >= 5000
