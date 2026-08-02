# URN: test:coach-ops:read-check-status:R001-UNIT-001-refused-query-ends-the-wait
# Acceptance: acc:coach-ops:R001-UNIT-001-refused-query-ends-the-wait
# WMBT: wmbt:coach-ops:R001
# Phase: RED
# Layer: application
# Runtime: python
"""R001-UNIT-001 — a CI read that failed for a reason waiting cannot change
must end the wait, not be polled.

``fetch_ci_status`` returns ``unknown`` for any gh failure it does not recognise,
and ``wait_for_ci`` exits only on ``pass`` or ``fail``. So a permanent fault — a
refused field, a dead credential, a pull request that does not exist — is
indistinguishable from a check still running, and gets spent as thirty minutes of
silence ending in ``no CI result after 1800s``.

The assertions deliberately do NOT pin a status string. Naming the new terminal
status is the implementer's call; what this acceptance governs is that the wait
ends on the first read, that nothing sleeps, and that gh's own stderr reaches the
operator. Pinning a literal here would be the test dictating the design.

The stderr blobs are verbatim from gh 2.96.0 (2026-07-02).
"""
from __future__ import annotations

import json
import subprocess

import pytest

from atdd.coach.commands import merge_cascade

pytestmark = [pytest.mark.platform]


# Verbatim gh 2.96.0 stderr for each permanent fault class.
STDERR_REFUSED_FIELD = (
    'Unknown JSON field: "conclusion"\n'
    "Available fields:\n"
    "  bucket\n  completedAt\n  description\n  event\n  link\n"
    "  name\n  startedAt\n  state\n  workflow\n"
)
STDERR_NO_SUCH_PR = (
    "GraphQL: Could not resolve to a PullRequest with the number of 99999999. "
    "(repository.pullRequest)\n"
)
STDERR_AUTH = (
    "error connecting to api.github.com\n"
    "check your internet connection or https://githubstatus.com\n"
)


class _Clock:
    """Monotonic fake: every read advances by ``step`` seconds."""

    def __init__(self, step: int = 30):
        self.step = step
        self.now = 0.0

    def __call__(self) -> float:
        value = self.now
        self.now += self.step
        return value


class _Sleeper:
    """Records what it was asked to sleep for, and never actually sleeps."""

    def __init__(self):
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


# Captured before any monkeypatching so the stubs can delegate. `subprocess.run`
# is process-global: intercepting every call would also swallow the conftest's
# autouse observer reaper, which runs during teardown while the patch is live.
_REAL_RUN = subprocess.run


def _install_gh(monkeypatch, *, stdout="[]", stderr="", returncode=0):
    """Intercept `gh` at the real process boundary; pass everything else through."""

    def _fake_run(argv, **kwargs):
        if not (argv and argv[0] == "gh"):
            return _REAL_RUN(argv, **kwargs)
        if returncode != 0 and kwargs.get("check"):
            raise subprocess.CalledProcessError(returncode, argv, stdout, stderr)
        return subprocess.CompletedProcess(argv, returncode, stdout, stderr)

    monkeypatch.setattr(merge_cascade.subprocess, "run", _fake_run)


def _wait(pr: int = 1610):
    """Drive `wait_for_ci` with observable sleep and clock; return (result, sleeper)."""
    sleeper = _Sleeper()
    result = merge_cascade.wait_for_ci(
        pr, poll_interval=30, timeout=1800, sleep=sleeper, clock=_Clock(30)
    )
    return result, sleeper


@pytest.mark.parametrize(
    "stderr, fingerprint",
    [
        pytest.param(STDERR_REFUSED_FIELD, "Unknown JSON field", id="refused-field"),
        pytest.param(STDERR_NO_SUCH_PR, "Could not resolve", id="no-such-pr"),
        pytest.param(STDERR_AUTH, "error connecting", id="unreachable-api"),
    ],
)
def test_permanent_gh_failure_ends_the_wait_without_sleeping(
    monkeypatch, stderr, fingerprint
):
    """Waiting cannot fix any of these, so the wait must not begin."""
    _install_gh(monkeypatch, stderr=stderr, returncode=1)

    result, sleeper = _wait()

    assert sleeper.calls == [], (
        f"a permanent gh failure was polled {len(sleeper.calls)} time(s) before "
        "giving up; nothing about it becomes true by waiting"
    )
    assert result.status not in {"merged", "timeout"}, (
        f"a permanent gh failure reported status {result.status!r} — a timeout "
        "reads as 'CI never finished' and hides a fault gh already diagnosed"
    )
    assert fingerprint in result.detail, (
        f"gh's own stderr did not reach the operator; detail was {result.detail!r}"
    )


def test_unparseable_payload_ends_the_wait(monkeypatch):
    """Garbage on stdout is terminal too — re-reading will not make it JSON."""
    _install_gh(monkeypatch, stdout="<!DOCTYPE html><html>502 Bad Gateway", returncode=0)

    result, sleeper = _wait()

    assert sleeper.calls == []
    assert result.status not in {"merged", "timeout"}


def test_no_required_checks_still_reads_as_pass(monkeypatch):
    """The benign case gh reports as an error must stay benign."""
    _install_gh(
        monkeypatch, stderr="no required checks reported on the 'main' branch\n", returncode=1
    )

    result, sleeper = _wait()

    assert result.status == "merged"
    assert sleeper.calls == []


def test_in_flight_check_still_polls_and_then_passes(monkeypatch):
    """The one outcome waiting CAN change must keep the loop alive."""
    pending = json.dumps([{"name": "validate-gate", "bucket": "pending", "state": "IN_PROGRESS"}])
    green = json.dumps([{"name": "validate-gate", "bucket": "pass", "state": "SUCCESS"}])
    responses = [pending, pending, green]

    def _fake_run(argv, **kwargs):
        if not (argv and argv[0] == "gh"):
            return _REAL_RUN(argv, **kwargs)
        body = responses.pop(0) if responses else green
        return subprocess.CompletedProcess(argv, 0, body, "")

    monkeypatch.setattr(merge_cascade.subprocess, "run", _fake_run)

    result, sleeper = _wait()

    assert result.status == "merged"
    assert len(sleeper.calls) == 2, (
        f"expected two polls before the check went green, got {sleeper.calls}"
    )
