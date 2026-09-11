# URN: test:govern-lifecycle:gh-credential-gate:E082-UNIT-001-status-is-a-hint-a-real-call-is-the-verdict
# Acceptance: acc:govern-lifecycle:E082-UNIT-001-status-is-a-hint-a-real-call-is-the-verdict
# WMBT: wmbt:govern-lifecycle:E082
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""E082-UNIT-001 — a credential that can do the work is not refused for failing to name itself.

RED: `_check_gh` runs `gh auth status` and raises on any non-zero exit. That
command resolves the IDENTITY — it calls `/user`. The Actions `GITHUB_TOKEN` is
an installation token that cannot call `/user` and can do every repo-scoped thing
it was issued for; a repo-scoped fine-grained PAT fails the same way. So the gate
refuses work the credential is able to do, and `result.stderr` — the only thing
that says which of the two actually failed — is discarded in favour of
`Run: gh auth login`, which in CI addresses nobody.

Observed on main at 435b398d: inside ONE CI job, the two tests in
test_y011_smoke_001 that call `gh api` directly passed while the three taking a
`GitHubClient` errored at construction. Same binary, same credential (#1937).

Each regime below pins a `gh` on PATH, so this is offline and deterministic.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

REPO = "afokapu/atdd"

# regime -> (auth status rc, auth status stderr, api rc, api stderr)
REGIMES = {
    "workstation": (0, "✓ Logged in to github.com account someone", 0, ""),
    # Cannot call /user; can do everything it was issued for. This is CI.
    "actions_token": (
        1,
        "X Failed to log in to github.com using token (GH_TOKEN)\n"
        "  - The token in GH_TOKEN is invalid for /user (HTTP 403)",
        0, "",
    ),
    # A repo-scoped fine-grained PAT: same shape, different cause.
    "narrow_scopes": (1, "X github.com: missing required scopes ['read:org']", 0, ""),
    "unauthenticated": (
        1, "You are not logged into any GitHub hosts. Run gh auth login to authenticate.",
        1, "gh: Requires authentication (HTTP 401)",
    ),
    "expired_token": (
        1, "X github.com: authentication failed - the token has expired",
        1, "gh: Bad credentials (HTTP 401)",
    ),
}

CAN_WORK = {"workstation", "actions_token", "narrow_scopes"}


def _shq(text: str) -> str:
    return "'" + text.replace("'", "'\\''") + "'"


@pytest.fixture
def gh_on_path(tmp_path, monkeypatch):
    """Install a stub `gh` for one regime and put ONLY it on PATH.

    Returns a callable so a test can pick its regime; also records every
    invocation, which is how the healthy-path call count is asserted.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = bin_dir / "calls.log"
    calls.write_text("", encoding="utf-8")

    def install(regime: str | None):
        if regime is None:  # gh absent entirely
            monkeypatch.setenv("PATH", str(bin_dir))
            return calls
        status_rc, status_err, api_rc, api_err = REGIMES[regime]
        gh = bin_dir / "gh"
        gh.write_text(
            "#!/bin/sh\n"
            f'echo "$@" >> {_shq(str(calls))}\n'
            'if [ "$1" = "auth" ] && [ "$2" = "status" ]; then\n'
            f"  printf '%s\\n' {_shq(status_err)} >&2\n  exit {status_rc}\nfi\n"
            'if [ "$1" = "api" ]; then\n'
            f"  printf '%s\\n' {_shq(api_err)} >&2\n"
            f"  [ {api_rc} -eq 0 ] && echo '[]'\n  exit {api_rc}\nfi\nexit 0\n",
            encoding="utf-8",
        )
        gh.chmod(0o755)
        monkeypatch.setenv("PATH", str(bin_dir))
        return calls

    return install


def _construct(repo: str = REPO):
    from atdd.coach.github import GitHubClient

    return GitHubClient(repo=repo)


@pytest.mark.parametrize("regime", sorted(CAN_WORK))
def test_a_credential_that_can_reach_the_api_constructs(gh_on_path, regime):
    """THE POINT. `actions_token` and `narrow_scopes` fail `gh auth status` and
    can still do the work — refusing them is refusing work that would succeed."""
    gh_on_path(regime)
    _construct()  # must not raise


@pytest.mark.parametrize("regime", sorted(set(REGIMES) - CAN_WORK))
def test_a_credential_that_cannot_reach_the_api_is_still_refused(gh_on_path, regime):
    """Nothing here loosens the gate: failing both checks is a real refusal."""
    from atdd.coach.github import GitHubClientError

    gh_on_path(regime)
    with pytest.raises(GitHubClientError):
        _construct()


def test_a_missing_gh_is_refused_and_names_the_install(gh_on_path):
    from atdd.coach.github import GitHubClientError

    gh_on_path(None)
    with pytest.raises(GitHubClientError, match="not found"):
        _construct()


def test_the_refusal_quotes_what_gh_actually_said(gh_on_path):
    """`Run: gh auth login` addresses nobody in CI, and the stderr that said why
    was thrown away. Whatever gh reported must survive into the message."""
    from atdd.coach.github import GitHubClientError

    gh_on_path("expired_token")
    with pytest.raises(GitHubClientError) as exc:
        _construct()
    message = str(exc.value)
    assert "expired" in message, f"gh's own diagnosis is missing:\n{message}"
    assert "401" in message or "Bad credentials" in message, message


def test_the_healthy_path_costs_exactly_one_gh_call(gh_on_path):
    """The fix must not put a network call on every construction — the client is
    built once per validator, so the green path pays it on every run."""
    calls = gh_on_path("workstation")
    _construct()
    invocations = [c for c in calls.read_text(encoding="utf-8").splitlines() if c.strip()]
    assert len(invocations) == 1, f"expected 1 gh call on the healthy path, got {invocations}"
    assert invocations[0].startswith("auth status"), invocations
