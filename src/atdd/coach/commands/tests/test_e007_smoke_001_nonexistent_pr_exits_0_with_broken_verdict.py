# URN: test:integration-hardening:integration-hardening:E007-SMOKE-001-nonexistent-pr-exits-0-with-broken-verdict
# Acceptance: acc:integration-hardening:E007-SMOKE-001-nonexistent-pr-exits-0-with-broken-verdict
# WMBT: wmbt:integration-hardening:E007
# Phase: SMOKE
# Layer: smoke
# Assertion: behavioral
"""E007-SMOKE-001 — a real non-existent PR exits 0 with a broken verdict.

Drives the real ``coach_review.run()`` with the real, gh-backed
``_resolve_pr_commit`` (no monkeypatch) against a PR number that does not
exist, so the actual ``gh pr view`` fails. Proves the in-process "always
exits 0" contract holds against an honest PR-resolution failure — equivalent
to ``atdd coach review 999999 --no-spawn --in-process --report-file <p>``.

This smoke test makes a live GitHub API call, so it is opt-in: set
``ATDD_SMOKE_REAL_GH=1`` to run it. It skips cleanly otherwise, or when the
``gh`` CLI is unavailable on the host.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

_NONEXISTENT_PR = 999999


def _opt_in_or_skip() -> None:
    if os.environ.get("ATDD_SMOKE_REAL_GH") != "1":
        pytest.skip(
            "ATDD_SMOKE_REAL_GH != 1 — real gh-backed PR-resolution smoke is "
            "opt-in (it makes a live GitHub API call)"
        )
    if shutil.which("gh") is None:
        pytest.skip("gh CLI not available on host")


class TestNonexistentPrExitsZeroWithBrokenVerdict:
    """Real coach_review.run() against a non-existent PR, in-process mode."""

    def _run(self, tmp_path: Path) -> tuple[int, Path]:
        _opt_in_or_skip()
        from atdd.coach.commands import coach_review

        report_path = tmp_path / "r.json"
        os.environ["ATDD_RUNTIME_ROOT"] = str(tmp_path / ".atdd" / "runtime")
        try:
            rc = coach_review.run(
                pr_number=_NONEXISTENT_PR,
                in_process=True,
                report_file=str(report_path),
            )
        finally:
            os.environ.pop("ATDD_RUNTIME_ROOT", None)
        return rc, report_path

    def test_exit_code_is_zero(self, tmp_path: Path):
        rc, _path = self._run(tmp_path)

        assert rc == 0, (
            "in-process mode must exit 0 against a non-existent PR — the real "
            f"gh pr view failure must route through the sentinel, got {rc}"
        )

    def test_report_file_is_valid_json(self, tmp_path: Path):
        _rc, report_path = self._run(tmp_path)

        assert report_path.exists(), f"report.json not written to {report_path}"
        json.loads(report_path.read_text())  # raises if not valid JSON

    def test_verdict_is_review_step_broken(self, tmp_path: Path):
        _rc, report_path = self._run(tmp_path)

        data = json.loads(report_path.read_text())
        assert data.get("verdict") == "review-step-broken", (
            f"expected verdict='review-step-broken', got {data.get('verdict')!r}"
        )

    def test_summary_is_non_empty(self, tmp_path: Path):
        _rc, report_path = self._run(tmp_path)

        data = json.loads(report_path.read_text())
        assert data.get("summary"), "expected a non-empty summary in report.json"
