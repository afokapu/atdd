# URN: test:integration-hardening:integration-hardening:E007-UNIT-002-pr-resolution-failure-spawn-path-still-returns-2
# Acceptance: acc:integration-hardening:E007-UNIT-002-pr-resolution-failure-spawn-path-still-returns-2
# WMBT: wmbt:integration-hardening:E007
# Phase: RED
# Layer: application
# Assertion: behavioral
"""E007-UNIT-002 — the spawn-based path is unchanged (true negative).

The E007 fix routes PR-resolution failures through ``_write_broken_sentinel``
**only in in-process mode**. The spawn-based path (``in_process=False``) has no
"exit 0 always" contract — it must keep returning ``2`` and must NOT write a
report file. This guards against the fix over-reaching into the spawn path.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


_RATE_LIMIT_ERROR = (
    "gh pr view 726 failed (rc=1): GraphQL: API rate limit already exceeded"
)


def _raise_rate_limit(*_args, **_kwargs):
    raise RuntimeError(_RATE_LIMIT_ERROR)


class TestPrResolutionFailureSpawnPathStillReturns2:
    """run(pr_number=N, in_process=False) with PR resolution forced to fail."""

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
            in_process=False,
            report_file=str(report_path),
        )
        return rc, report_path

    def test_exit_code_is_two(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        rc, _path = self._run(tmp_path, monkeypatch)

        assert rc == 2, (
            "the spawn-based path has no 'exit 0 always' contract — a "
            f"PR-resolution failure must keep returning 2, got {rc}"
        )

    def test_no_report_file_written(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        _rc, report_path = self._run(tmp_path, monkeypatch)

        assert not report_path.exists(), (
            "the spawn-based path must NOT write a sentinel report.json on a "
            f"PR-resolution failure — found one at {report_path}"
        )
