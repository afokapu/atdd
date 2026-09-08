# URN: test:coach-ops:read-check-status:R001-SMOKE-001-real-gh-error-ends-the-wait-on-the-first-read
# Acceptance: acc:coach-ops:R001-SMOKE-001-real-gh-error-ends-the-wait-on-the-first-read
# WMBT: wmbt:coach-ops:R001
# Phase: SMOKE
# Layer: application
# Runtime: python
"""R001-SMOKE-001 — against the real ``gh``, a failure waiting cannot fix ends
the wait on the first read.

The unit sibling proves this with a canned ``CalledProcessError``. This one asks
the real binary for a pull request that does not exist and lets GitHub produce
the error itself, so the classification is exercised against a fault the API
actually emits rather than one the test invented.

Nothing about ``gh`` is stubbed. ``sleep`` and ``clock`` are injected purely as
observers — the recording sleeper never waits, so a failure here costs seconds
rather than the 1800s the defect costs an operator.

Scope note (deliberate, recorded at RED): this exercises the shipped
``wait_for_ci``, not the whole ``atdd merge-cascade`` CLI. ``cascade()`` runs
``update_branch`` first and halts there for an unresolvable pull request, so a
CLI-level test would never reach the CI read and would pass for the wrong
reason. See the ``revision_reason`` on this acceptance in
``plan/coach_ops/R001.yaml``.
"""
from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from atdd.coach.commands import merge_cascade

pytestmark = [pytest.mark.platform, pytest.mark.smoke]


# A pull request number this repository will never reach.
UNRESOLVABLE_PR = 99999999

_REAL_RUN = subprocess.run


def _gh(*args: str) -> subprocess.CompletedProcess:
    return _REAL_RUN(["gh", *args], capture_output=True, text=True)


@pytest.fixture(scope="module")
def live_gh() -> None:
    """Skip only when the real environment cannot answer at all."""
    if shutil.which("gh") is None:
        pytest.skip("gh is not on PATH — no installed CLI to interrogate")
    if _gh("auth", "status").returncode != 0:
        pytest.skip("gh is not authenticated — cannot reach the GitHub API")


@pytest.fixture(scope="module")
def unresolvable_is_really_unresolvable(live_gh) -> str:
    """Confirm with the live API that the number really does not resolve.

    Guards against the test passing — or failing — because of some *other*
    failure: it pins that the fault under test is the one GitHub emits for a
    missing PR, not whatever else the API happens to be saying today.

    An exhausted GraphQL quota is the environment being unable to answer, so it
    skips. Any other unexpected failure mode still fails loudly: the difference
    matters, because a rate-limit error would otherwise be silently accepted as
    evidence for a claim about missing pull requests.
    """
    probe = _gh("pr", "checks", str(UNRESOLVABLE_PR), "--json", "state")
    if "rate limit" in (probe.stderr or "").lower():
        pytest.skip(
            "GitHub GraphQL quota is exhausted, so the API cannot report whether "
            f"PR #{UNRESOLVABLE_PR} resolves: {probe.stderr.strip()}"
        )
    assert probe.returncode != 0, (
        f"PR #{UNRESOLVABLE_PR} unexpectedly resolves; pick a higher number"
    )
    assert "Could not resolve" in probe.stderr, (
        f"unexpected gh failure mode for a missing PR: {probe.stderr!r}"
    )
    return probe.stderr


class _Sleeper:
    """Records what it was asked to sleep for, and never actually sleeps."""

    def __init__(self):
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


class _Clock:
    """Monotonic fake so the loop is bounded without the test ever waiting."""

    def __init__(self, step: int = 1):
        self.step = step
        self.now = 0.0

    def __call__(self) -> float:
        value = self.now
        self.now += self.step
        return value


def _wait(pr: int):
    sleeper = _Sleeper()
    result = merge_cascade.wait_for_ci(
        pr, poll_interval=1, timeout=3, sleep=sleeper, clock=_Clock(1)
    )
    return result, sleeper


def test_unresolvable_pull_request_ends_the_wait_on_the_first_read(
    live_gh, unresolvable_is_really_unresolvable
):
    """Real gh says the PR does not exist; polling that is pure waste."""
    result, sleeper = _wait(UNRESOLVABLE_PR)

    assert sleeper.calls == [], (
        f"a pull request GitHub says does not exist was polled "
        f"{len(sleeper.calls)} time(s); at the production 30s interval that is "
        "half an hour spent on a fault gh diagnosed immediately"
    )
    assert result.status not in {"merged", "timeout"}, (
        f"status was {result.status!r} — 'timeout' reads as 'CI never finished' "
        "and hides an error GitHub already reported"
    )


def test_the_real_gh_error_reaches_the_operator(
    live_gh, unresolvable_is_really_unresolvable
):
    """The operator should read GitHub's diagnosis, not a stopwatch."""
    result, _ = _wait(UNRESOLVABLE_PR)

    assert "Could not resolve" in result.detail, (
        "gh's own error did not survive into the reported detail; the operator "
        f"sees {result.detail!r} instead of GitHub's explanation"
    )
    assert "no CI result after" not in result.detail


def test_a_pull_request_that_exists_still_reaches_a_verdict(live_gh):
    """Ending the wait must be scoped to real failures, not swallow a working read."""
    listing = _gh("pr", "list", "--state", "all", "--limit", "1", "--json", "number")
    if listing.returncode != 0:
        pytest.skip(f"could not list pull requests: {listing.stderr.strip()}")
    entries = json.loads(listing.stdout or "[]")
    if not entries:
        pytest.skip("this repository has no pull requests to read checks for")

    state, detail = merge_cascade.fetch_ci_status(int(entries[0]["number"]))

    assert state in {"pass", "fail", "pending"}, (
        f"a readable pull request produced state={state!r} detail={detail!r}; "
        "the terminal-error path must not consume a read that actually worked"
    )
