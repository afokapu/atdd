# URN: test:integration-hardening:integration-hardening:E008-UNIT-001-pr-resolution-failure-in-process-writes-sentinel
# Acceptance: acc:integration-hardening:E008-UNIT-001-pr-resolution-failure-in-process-writes-sentinel
# WMBT: wmbt:integration-hardening:E008
# Phase: RED
# Layer: application
# Assertion: behavioral
"""E008-UNIT-001 — a PR-resolution failure in in-process mode writes a
``review-step-broken`` sentinel and exits 0.

``atdd coach review <N> --no-spawn --in-process --report-file <path>`` promises
*"Always exits 0; verdict is in the report file"*. But ``run()`` step 1 resolves
the PR commit **before** the ``if in_process:`` dispatch, and a ``_resolve_pr_commit``
``RuntimeError`` (gh rate limit, network failure, missing PR) currently escapes
with ``return 2`` and no report file — bypassing ``_write_broken_sentinel``.

This test forces that failure and asserts the in-process contract holds: exit 0
and a ``review-step-broken`` report at ``--report-file``.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


_RATE_LIMIT_ERROR = (
    "gh pr view 726 failed (rc=1): GraphQL: API rate limit already exceeded"
)


def _raise_rate_limit(*_args, **_kwargs):
    raise RuntimeError(_RATE_LIMIT_ERROR)


class TestPrResolutionFailureInProcessWritesSentinel:
    """run(pr_number=N, in_process=True) with PR resolution forced to fail."""

    def _run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> tuple[int, Path]:
        from atdd.coach.commands import coach_review

        report_path = tmp_path / "review.json"
        monkeypatch.setenv("ATDD_RUNTIME_ROOT", str(tmp_path / ".atdd" / "runtime"))
        monkeypatch.setattr(coach_review, "_resolve_pr_commit", _raise_rate_limit)
        monkeypatch.setattr(coach_review, "_print", lambda msg: None)
        monkeypatch.setattr(coach_review, "_print_err", lambda msg: None)

        rc = coach_review.run(
            pr_number=726,
            in_process=True,
            report_file=str(report_path),
        )
        return rc, report_path

    def test_exit_code_is_zero(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        rc, _path = self._run(tmp_path, monkeypatch)

        assert rc == 0, (
            "in-process mode must exit 0 even when PR resolution fails — "
            f"the documented contract is 'always exits 0', got {rc}"
        )

    def test_report_file_exists(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        _rc, report_path = self._run(tmp_path, monkeypatch)

        assert report_path.exists(), (
            f"a sentinel report.json must be written to --report-file "
            f"({report_path}) when PR resolution fails in in-process mode"
        )

    def test_verdict_is_review_step_broken(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        _rc, report_path = self._run(tmp_path, monkeypatch)

        data = json.loads(report_path.read_text())
        assert data.get("verdict") == "review-step-broken", (
            "PR-resolution failure must produce a 'review-step-broken' verdict, "
            f"got {data.get('verdict')!r}"
        )

    def test_summary_is_non_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        _rc, report_path = self._run(tmp_path, monkeypatch)

        data = json.loads(report_path.read_text())
        assert data.get("summary"), (
            "the sentinel report must carry a non-empty diagnostic summary"
        )
