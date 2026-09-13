# URN: test:govern-lifecycle:gh-credential-gate:E082-SMOKE-001-the-real-gh-on-this-machine-constructs-a-client
# Acceptance: acc:govern-lifecycle:E082-SMOKE-001-the-real-gh-on-this-machine-constructs-a-client
# WMBT: wmbt:govern-lifecycle:E082
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E082-SMOKE-001 — the gate agrees with the real credential, whatever it is.

The unit test fixes gh's behaviour per regime. This one takes the credential this
machine (or this CI job) actually holds and asserts the only invariant that
matters: if a direct repo-scoped call succeeds, the client must construct.

Deliberately NOT marked `github_api`. The whole defect was a client refusing to
exist in a job where the API worked, and the two tests that caught it first were
the ones making real calls. A test that skips wherever the credential is
interesting would not have caught it — a skipped test is green (#1896).
"""
from __future__ import annotations

import subprocess

import pytest

from atdd.coach.github import GitHubClient, GitHubClientError

pytestmark = [pytest.mark.platform]

REPO = "afokapu/atdd"


def _gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True, timeout=30)


def test_the_gate_never_refuses_a_credential_a_direct_call_proves_usable():
    """THE POINT, against whatever credential is really in play here."""
    try:
        direct = _gh("api", f"repos/{REPO}", "--jq", ".name")
    except FileNotFoundError:
        pytest.skip("gh is not installed on this machine — nothing to compare against")

    if direct.returncode != 0:
        pytest.skip(
            "this machine's credential cannot reach the API, so there is no "
            f"usable-but-refused case to test: {direct.stderr.strip()[:200]}"
        )

    # The direct call worked. The gate must not disagree with that.
    try:
        GitHubClient(repo=REPO)
    except GitHubClientError as exc:
        status = _gh("auth", "status")
        pytest.fail(
            "a direct repos/ call succeeded but GitHubClient refused to construct — "
            "the gate is refusing work the credential can do.\n"
            f"gate said: {exc}\n"
            f"gh auth status rc={status.returncode}: {status.stderr.strip()[:300]}"
        )
