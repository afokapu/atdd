# URN: test:govern-lifecycle:issue-fetches-refuse-to-truncate:E077-SMOKE-001-the-live-fetch-returns-every-issue
# Acceptance: acc:govern-lifecycle:E077-SMOKE-001-the-live-fetch-returns-every-issue
# WMBT: wmbt:govern-lifecycle:E077
# Phase: SMOKE
# Layer: integration
"""E077-SMOKE-001 — the live fetch returns every issue, not the newest page (#1903).

The UNIT test stubs the row count. This one counts the repository independently,
through a PAGINATED REST call, and compares. That independence is the point: the
defect was a fetch that agreed with itself, and a test using the same capped path
to establish the expected number would have agreed with it too.

Marked `github_api` — one real, paginated census per run.
"""
from __future__ import annotations

import subprocess

import pytest

from atdd.coach.github import GitHubClient

pytestmark = [pytest.mark.platform, pytest.mark.github_api]

REPO = "afokapu/atdd"


def _census(extra: str = "") -> int:
    """Count open issues via a paginated REST call — independent of the client."""
    out = subprocess.run(
        ["gh", "api", f"repos/{REPO}/issues?state=open&per_page=100{extra}",
         "--paginate", "--jq", ".[]|select(.pull_request==null)|.number"],
        capture_output=True, text=True, check=True,
    ).stdout.split()
    return len(out)


@pytest.fixture(scope="module")
def client() -> GitHubClient:
    return GitHubClient(repo=REPO)


def test_the_label_filtered_listing_matches_an_independent_census(client) -> None:
    expected = _census("&labels=atdd-issue")
    got = len(client.list_issues_by_label("atdd-issue", include_body=False))
    assert got == expected, (
        f"the client returned {got} of {expected} labelled issues — a prefix read "
        "as the whole answer"
    )


def test_the_unfiltered_listing_matches_an_independent_census(client) -> None:
    expected = _census()
    got = len(client.list_all_open_issues())
    assert got == expected, f"the client returned {got} of {expected} open issues"


def test_issues_outside_the_newest_hundred_are_present(client) -> None:
    """THE POINT: the old cap kept the NEWEST 100, so the oldest issues — the ones
    least likely to be re-examined — were the ones it silently dropped."""
    numbers = sorted(i["number"] for i in client.list_issues_by_label("atdd-issue", include_body=False))
    if len(numbers) <= 100:
        pytest.skip("repository is at or below the old cap; nothing was being dropped")
    newest_hundred = set(numbers[-100:])
    older = [n for n in numbers if n not in newest_hundred]
    assert older, "no issues outside the newest hundred, so this proves nothing"
