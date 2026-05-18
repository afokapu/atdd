# URN: test:integration-hardening:integration-hardening:E008-UNIT-003-sentinel-summary-names-pr-resolution
# Acceptance: acc:integration-hardening:E008-UNIT-003-sentinel-summary-names-pr-resolution
# WMBT: wmbt:integration-hardening:E008
# Phase: RED
# Layer: application
# Assertion: behavioral
"""E008-UNIT-003 — the PR-resolution sentinel carries a diagnostic summary.

When ``run()`` writes a ``review-step-broken`` sentinel for a PR-resolution
failure, the report must name the *PR-resolution* failure and surface the
underlying ``gh`` error, so operators can tell a transient infra hiccup
(rate limit) apart from a genuine review failure.
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


class TestSentinelSummaryNamesPrResolution:
    """The sentinel diagnostic text identifies the PR-resolution failure."""

    def _diagnostic_text(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> str:
        from atdd.coach.commands import coach_review

        report_path = tmp_path / "review.json"
        monkeypatch.setenv("ATDD_RUNTIME_ROOT", str(tmp_path / ".atdd" / "runtime"))
        monkeypatch.setattr(coach_review, "_resolve_pr_commit", _raise_rate_limit)
        monkeypatch.setattr(coach_review, "_print", lambda msg: None)
        monkeypatch.setattr(coach_review, "_print_err", lambda msg: None)

        coach_review.run(
            pr_number=726,
            in_process=True,
            report_file=str(report_path),
        )

        data = json.loads(report_path.read_text())
        # The acceptance allows the diagnostic to land in summary or error.
        return f"{data.get('summary', '')}\n{data.get('error', '')}"

    def test_diagnostic_names_pr_resolution(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        text = self._diagnostic_text(tmp_path, monkeypatch)

        assert "PR resolution" in text, (
            "the sentinel summary/error must name the 'PR resolution' failure "
            f"so operators know which step broke — got: {text!r}"
        )

    def test_diagnostic_surfaces_underlying_gh_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        text = self._diagnostic_text(tmp_path, monkeypatch)

        assert "rate limit" in text, (
            "the sentinel summary/error must surface the underlying gh error "
            f"('rate limit') so transient infra hiccups are distinguishable — "
            f"got: {text!r}"
        )
