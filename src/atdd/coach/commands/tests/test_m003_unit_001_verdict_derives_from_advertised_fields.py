# URN: test:coach-ops:read-check-status:M003-UNIT-001-verdict-derives-from-advertised-fields
# Acceptance: acc:coach-ops:M003-UNIT-001-verdict-derives-from-advertised-fields
# WMBT: wmbt:coach-ops:M003
# Phase: RED
# Layer: integration
# Runtime: python
"""M003-UNIT-001 — the required-check verdict is derived only from fields the
installed ``gh`` advertises, and the query the tool sends names nothing else.

``fetch_ci_status`` asks ``gh pr checks`` for ``state,name,conclusion``. gh 2.96.0
does not advertise ``conclusion`` on this command, so the call exits 1 and no
verdict is ever read. Its semantic successor is ``bucket``.

The stub here replaces ``subprocess.run`` — the real process boundary — rather
than ``_run_gh``, so the argv these tests assert on is exactly the argv the ``gh``
process would receive. ``ADVERTISED_FIELDS`` is recorded from a live gh so this
file needs no network; ``acc:coach-ops:M003-SMOKE-001`` is what keeps that
recording honest against the gh actually installed.

Not every function here fails today. The two that do — the field list and the
failing-check verdict — are the defect; the rest pin behaviour that is currently
correct only by accident of ``conclusion`` always being empty, and would regress
the moment the verdict moves to ``bucket`` carelessly.
"""
from __future__ import annotations

import json
import subprocess

import pytest

from atdd.coach.commands import merge_cascade

pytestmark = [pytest.mark.platform]


# The field set `gh pr checks --json` advertises on gh 2.96.0 (2026-07-02),
# read out of gh's own refusal message. `conclusion` is deliberately absent.
ADVERTISED_FIELDS = frozenset(
    {
        "bucket",
        "completedAt",
        "description",
        "event",
        "link",
        "name",
        "startedAt",
        "state",
        "workflow",
    }
)


def _check(name: str, bucket: str, state: str) -> dict:
    """One `gh pr checks --json` row, shaped as gh actually returns it."""
    return {"name": name, "bucket": bucket, "state": state}


# Captured before any monkeypatching so the spy can delegate. `subprocess.run` is
# process-global: intercepting every call would also swallow the conftest's autouse
# observer reaper, which runs during teardown while the patch is live.
_REAL_RUN = subprocess.run


class _GhSpy:
    """Stand in for ``subprocess.run``: record argv, return a canned result.

    Only ``gh`` is intercepted; every other command passes through untouched.
    """

    def __init__(self, stdout: str = "[]", stderr: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.calls: list[list[str]] = []

    def __call__(self, argv, **kwargs):
        if not (argv and argv[0] == "gh"):
            return _REAL_RUN(argv, **kwargs)
        self.calls.append(list(argv))
        if self.returncode != 0 and kwargs.get("check"):
            raise subprocess.CalledProcessError(
                self.returncode, argv, self.stdout, self.stderr
            )
        return subprocess.CompletedProcess(
            argv, self.returncode, self.stdout, self.stderr
        )

    @property
    def requested_fields(self) -> list[str]:
        """The `--json` field list of the last recorded invocation."""
        argv = self.calls[-1]
        return argv[argv.index("--json") + 1].split(",")


@pytest.fixture
def gh(monkeypatch):
    """Install a `_GhSpy` over the real process boundary and hand it back."""

    def _install(payload=None, stdout=None, stderr="", returncode=0) -> _GhSpy:
        body = stdout if stdout is not None else json.dumps(payload or [])
        spy = _GhSpy(stdout=body, stderr=stderr, returncode=returncode)
        monkeypatch.setattr(merge_cascade.subprocess, "run", spy)
        return spy

    return _install


def test_requested_json_fields_are_all_advertised_by_gh(gh):
    """Every field asked for exists on the installed gh — `conclusion` does not."""
    spy = gh(payload=[_check("validate-gate", "pass", "SUCCESS")])

    merge_cascade.fetch_ci_status(1610)

    requested = set(spy.requested_fields)
    assert "conclusion" not in requested, (
        "fetch_ci_status asks gh for 'conclusion', which gh 2.96.0 does not "
        "advertise on `pr checks`; the call exits 1 and reads nothing"
    )
    assert requested <= ADVERTISED_FIELDS, (
        f"fetch_ci_status asks gh for unadvertised field(s): "
        f"{sorted(requested - ADVERTISED_FIELDS)}"
    )


def test_failing_bucket_reads_as_fail_and_names_the_check(gh):
    """A red required check must read as `fail`, and say which check went red."""
    gh(
        payload=[
            _check("validate-gate", "pass", "SUCCESS"),
            _check("auto-phase", "fail", "FAILURE"),
        ]
    )

    state, detail = merge_cascade.fetch_ci_status(1610)

    assert state == "fail", (
        f"a check with bucket 'fail' read as {state!r} — the verdict is still "
        "derived from 'conclusion', which gh no longer returns, so every check "
        "looks green"
    )
    assert "auto-phase" in detail


def test_all_passing_buckets_read_as_pass(gh):
    """Every check green reads as `pass` and counts them."""
    gh(
        payload=[
            _check("validate-gate", "pass", "SUCCESS"),
            _check("validate-coach", "pass", "SUCCESS"),
        ]
    )

    state, detail = merge_cascade.fetch_ci_status(1610)

    assert state == "pass"
    assert "2" in detail


def test_in_flight_bucket_reads_as_pending(gh):
    """A check still running reads as `pending` — the one pollable outcome."""
    gh(
        payload=[
            _check("validate-gate", "pass", "SUCCESS"),
            _check("validate-coach", "pending", "IN_PROGRESS"),
        ]
    )

    state, _ = merge_cascade.fetch_ci_status(1610)

    assert state == "pending"


def test_empty_required_check_list_reads_as_pass(gh):
    """A PR with no required checks is not a PR that is failing."""
    gh(payload=[])

    state, detail = merge_cascade.fetch_ci_status(1610)

    assert state == "pass"
    assert "no required checks" in detail


def test_skipped_required_check_is_not_a_failure(gh):
    """`skipping`/`cancel` are not `fail` — GitHub treats such a PR as mergeable."""
    gh(
        payload=[
            _check("validate-gate", "pass", "SUCCESS"),
            _check("shadow-drift", "skipping", "SKIPPED"),
        ]
    )

    state, detail = merge_cascade.fetch_ci_status(1610)

    assert state != "fail", (
        f"a skipped required check read as fail ({detail!r}); GitHub itself "
        "treats the PR as satisfiable, so the cascade must not halt on it"
    )
