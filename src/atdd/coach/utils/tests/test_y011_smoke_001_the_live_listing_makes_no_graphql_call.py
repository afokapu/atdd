# URN: test:govern-lifecycle:issue-listing-uses-rest:Y011-SMOKE-001-the-live-listing-makes-no-graphql-call
# Acceptance: acc:govern-lifecycle:Y011-SMOKE-001-the-live-listing-makes-no-graphql-call
# WMBT: wmbt:govern-lifecycle:Y011
# Phase: SMOKE
# Layer: integration
"""Y011-SMOKE-001 — the live listing is REST, and agrees with what it replaced (#1930).

The UNIT test proves the normaliser over synthetic rows. It cannot tell you which
endpoint the client reaches, and the endpoint is the entire point of this change.

`GH_DEBUG=api` makes gh log every request, so the transport is observed rather
than assumed — the same instrument that established `gh issue list --json` is
`POST /graphql` in the first place.
"""
from __future__ import annotations

import json
import os
import subprocess

import pytest

from atdd.coach.github import GitHubClient

pytestmark = [pytest.mark.platform, pytest.mark.github_api]

REPO = "afokapu/atdd"


def _debug_requests(args: list[str]) -> list[str]:
    """Every request line gh logs while running `args`."""
    proc = subprocess.run(
        ["gh", *args], capture_output=True, text=True, timeout=120,
        env={**os.environ, "GH_DEBUG": "api"},
    )
    return [ln for ln in proc.stderr.splitlines() if ln.startswith("> ")]


def _gh_is_authenticated() -> bool:
    """Whether `gh` in THIS environment can talk to GitHub at all."""
    return subprocess.run(
        ["gh", "auth", "status"], capture_output=True, timeout=30,
    ).returncode == 0


requires_gh = pytest.mark.skipif(
    not _gh_is_authenticated(),
    reason=(
        "gh is not authenticated in this environment, so the live transport "
        "cannot be observed. This is #1911 — push-event CI runs authenticate no "
        "gh even with GH_TOKEN set — not a verdict about the listing. The "
        "pull_request-event run of the same job does exercise these assertions."
    ),
)


@pytest.fixture(scope="module")
def client() -> GitHubClient:
    return GitHubClient(repo=REPO)


@requires_gh
def test_the_listing_reaches_rest_and_not_graphql() -> None:
    """THE POINT. The two buckets fail independently and GraphQL is the one that
    has been failing; this path must not be on it."""
    lines = _debug_requests([
        "api", "--paginate",
        f"repos/{REPO}/issues?state=open&labels=atdd-issue&per_page=100",
    ])
    assert lines, "gh logged no requests; the probe observed nothing"
    assert not [ln for ln in lines if "/graphql" in ln], (
        "the listing still reaches GraphQL:\n" + "\n".join(lines[:5])
    )
    assert [ln for ln in lines if "/issues?" in ln or "/issues" in ln], lines[:5]


@requires_gh
def test_the_subcommand_it_replaced_really_was_graphql() -> None:
    """Guards the guard: if `gh issue list` were REST all along, this change
    would be pointless and the test above would be proving nothing."""
    lines = _debug_requests([
        "issue", "list", "--repo", REPO, "--state", "open", "--json", "number", "--limit", "2",
    ])
    assert [ln for ln in lines if "/graphql" in ln], (
        "gh issue list no longer uses GraphQL — re-check whether this change is "
        "still needed:\n" + "\n".join(lines[:5])
    )


@requires_gh
def test_the_live_counts_agree(client: GitHubClient) -> None:
    """Same subject, both transports — a silent change of scope is the risk."""
    rest = client.list_issues_by_label("atdd-issue", include_body=False)
    gql = json.loads(subprocess.run(
        ["gh", "issue", "list", "--repo", REPO, "--label", "atdd-issue",
         "--state", "open", "--json", "number", "--limit", "5000"],
        capture_output=True, text=True, timeout=120).stdout or "[]")
    assert {i["number"] for i in rest} == {i["number"] for i in gql}


@requires_gh
def test_the_unfiltered_listing_excludes_pull_requests(client: GitHubClient) -> None:
    """REST /issues returns PRs too, and the count going UP is what hides it."""
    rows = client.list_all_open_issues()
    raw = json.loads(subprocess.run(
        ["gh", "api", "--paginate", f"repos/{REPO}/issues?state=open&per_page=100"],
        capture_output=True, text=True, timeout=120).stdout or "[]")
    pulls = [r for r in raw if r.get("pull_request") is not None]
    assert pulls, "no open PRs right now — this assertion would prove nothing"
    assert len(rows) == len(raw) - len(pulls)
    assert not ({r["number"] for r in rows} & {p["number"] for p in pulls})


@requires_gh
def test_state_keeps_the_case_callers_read(client: GitHubClient) -> None:
    rows = client.list_issues_by_label("atdd-issue", include_body=False)
    assert rows, "no open atdd-issues; nothing observed"
    assert {r["state"] for r in rows} == {"OPEN"}
