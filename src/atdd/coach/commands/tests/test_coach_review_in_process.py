# URN: test:integration-hardening:integration-hardening:E005-UNIT-001-in-process-flag-parsed
# Acceptance: acc:integration-hardening:E005-UNIT-001-in-process-flag-parsed
# Acceptance: acc:integration-hardening:E005-INTEGRATION-001-in-process-mode-works-without-cmux
# Acceptance: acc:integration-hardening:E005-INTEGRATION-004-review-step-broken-sentinel
# WMBT: wmbt:integration-hardening:E005
# Phase: RED
# Layer: application
# Assertion: behavioral
"""E005 unit + integration tests for atdd coach review --no-spawn/--in-process mode.

Covers:
- E005-UNIT-001: CLI argparse picks up --no-spawn/--in-process flags
- E005-INTEGRATION-001: in-process mode exits 0, writes report.json with valid verdict
- E005-INTEGRATION-004: when LLM unavailable, writes review-step-broken sentinel, exits 0
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

pytestmark = [pytest.mark.platform]


# ---------------------------------------------------------------------------
# Fixtures and stubs
# ---------------------------------------------------------------------------

_PASS_RESPONSE = {"verdict": "pass", "summary": "Changes look good."}
_CONCERN_RESPONSE = {"verdict": "concern", "summary": "Minor style issues noted."}
_FAIL_RESPONSE = {"verdict": "fail", "summary": "Missing test coverage."}


class _FakeLLMClient:
    def __init__(self, response: Any) -> None:
        self._response = response

    def invoke(self, prompt: str) -> Any:
        return self._response


class _LLMUnavailableClient:
    def invoke(self, prompt: str) -> Any:
        from atdd.coach.commands.judge import LLMUnavailable
        raise LLMUnavailable("test: LLM not available")


def _register_fake_llm(monkeypatch: pytest.MonkeyPatch, response: Any) -> None:
    from atdd.coach.commands import judge as judge_mod
    monkeypatch.setitem(judge_mod.LLM_REGISTRY, "fake-llm", lambda: _FakeLLMClient(response))


def _register_unavailable_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    from atdd.coach.commands import judge as judge_mod
    monkeypatch.setitem(judge_mod.LLM_REGISTRY, "fake-llm", lambda: _LLMUnavailableClient())


# ---------------------------------------------------------------------------
# E005-UNIT-001: flag parsing
# ---------------------------------------------------------------------------


class TestInProcessFlagParsed:
    def test_no_spawn_sets_in_process_true(self):
        from atdd.coach.commands.coach_review import parse_cli

        ns = parse_cli(["123", "--no-spawn"])
        assert ns.in_process is True, f"expected in_process=True, got {ns.in_process!r}"

    def test_in_process_sets_in_process_true(self):
        from atdd.coach.commands.coach_review import parse_cli

        ns = parse_cli(["123", "--in-process"])
        assert ns.in_process is True, f"expected in_process=True, got {ns.in_process!r}"

    def test_default_is_spawn_based(self):
        from atdd.coach.commands.coach_review import parse_cli

        ns = parse_cli(["123"])
        assert ns.in_process is False, f"expected in_process=False by default, got {ns.in_process!r}"

    def test_no_spawn_and_in_process_both_work(self):
        from atdd.coach.commands.coach_review import parse_cli

        for flag in ["--no-spawn", "--in-process"]:
            ns = parse_cli(["123", flag])
            assert ns.in_process is True, f"flag {flag!r} should set in_process=True"


# ---------------------------------------------------------------------------
# E005-INTEGRATION-001: in-process mode produces report.json, exits 0
# ---------------------------------------------------------------------------


class TestInProcessModeWorksWithoutCmux:
    def _run(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        llm_response: Any,
        pr_number: int = 123,
    ) -> tuple[int, Path]:
        from atdd.coach.commands import coach_review

        report_path = tmp_path / "review.json"
        monkeypatch.setenv("ATDD_RUNTIME_ROOT", str(tmp_path / ".atdd" / "runtime"))
        monkeypatch.setattr(
            coach_review, "_resolve_pr_commit", lambda _pr: "deadbeef01234567"
        )
        monkeypatch.setattr(
            coach_review, "_get_pr_diff", lambda **_kw: "# fake diff"
        )
        _register_fake_llm(monkeypatch, llm_response)
        monkeypatch.setattr(coach_review, "_print", lambda msg: None)
        monkeypatch.setattr(coach_review, "_print_err", lambda msg: None)

        rc = coach_review.run(
            pr_number=pr_number,
            in_process=True,
            report_file=str(report_path),
        )
        return rc, report_path

    def test_exits_zero_on_pass_verdict(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        rc, report_path = self._run(tmp_path, monkeypatch, _PASS_RESPONSE)

        assert rc == 0, f"expected exit 0 for pass verdict in in-process mode, got {rc}"

    def test_exits_zero_on_fail_verdict(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        rc, report_path = self._run(tmp_path, monkeypatch, _FAIL_RESPONSE)

        assert rc == 0, (
            "expected exit 0 in in-process mode even for fail verdict "
            "(enforce step reads the file, not the exit code)"
        )

    def test_exits_zero_on_concern_verdict(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        rc, report_path = self._run(tmp_path, monkeypatch, _CONCERN_RESPONSE)

        assert rc == 0, f"expected exit 0 for concern verdict in in-process mode, got {rc}"

    def test_report_file_written(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        _rc, report_path = self._run(tmp_path, monkeypatch, _PASS_RESPONSE)

        assert report_path.exists(), f"report.json not written to {report_path}"

    def test_report_verdict_valid(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        _rc, report_path = self._run(tmp_path, monkeypatch, _PASS_RESPONSE)

        data = json.loads(report_path.read_text())
        assert data.get("verdict") in ("pass", "concern", "fail"), (
            f"expected verdict in {{pass, concern, fail}}, got {data.get('verdict')!r}"
        )

    def test_report_summary_non_empty(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        _rc, report_path = self._run(tmp_path, monkeypatch, _PASS_RESPONSE)

        data = json.loads(report_path.read_text())
        assert data.get("summary"), "expected non-empty summary in report.json"

    def test_report_verdict_matches_llm_response(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        for response in (_PASS_RESPONSE, _CONCERN_RESPONSE, _FAIL_RESPONSE):
            _rc, report_path = self._run(tmp_path, monkeypatch, response)
            data = json.loads(report_path.read_text())
            assert data.get("verdict") == response["verdict"], (
                f"expected verdict={response['verdict']!r}, got {data.get('verdict')!r}"
            )
            report_path.unlink(missing_ok=True)

    def test_no_cmux_spawn_attempted(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        from atdd.coach.commands import coach_review

        spawned: list[str] = []
        monkeypatch.setattr(
            coach_review,
            "_spawn_reviewer_agent",
            lambda *args, **kwargs: spawned.append("spawned"),
        )
        self._run(tmp_path, monkeypatch, _PASS_RESPONSE)

        assert spawned == [], "in-process mode must not call _spawn_reviewer_agent"


# ---------------------------------------------------------------------------
# E005-INTEGRATION-004: review-step-broken sentinel when LLM unavailable
# ---------------------------------------------------------------------------


class TestReviewStepBrokenSentinel:
    def _run_no_llm(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        *,
        clear_registry: bool = True,
    ) -> tuple[int, Path]:
        from atdd.coach.commands import coach_review, judge as judge_mod

        report_path = tmp_path / "review.json"
        monkeypatch.setenv("ATDD_RUNTIME_ROOT", str(tmp_path / ".atdd" / "runtime"))
        monkeypatch.setattr(
            coach_review, "_resolve_pr_commit", lambda _pr: "deadbeef01234567"
        )
        monkeypatch.setattr(
            coach_review, "_get_pr_diff", lambda **_kw: "# fake diff"
        )
        if clear_registry:
            monkeypatch.setattr(judge_mod, "LLM_REGISTRY", {})
        monkeypatch.setattr(coach_review, "_print", lambda msg: None)
        monkeypatch.setattr(coach_review, "_print_err", lambda msg: None)

        rc = coach_review.run(
            pr_number=123,
            in_process=True,
            report_file=str(report_path),
        )
        return rc, report_path

    def test_exits_zero_when_no_llm(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        rc, _path = self._run_no_llm(tmp_path, monkeypatch)

        assert rc == 0, (
            f"expected exit 0 for review-step-broken sentinel (no LLM), got {rc}"
        )

    def test_sentinel_written_when_no_llm(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        _rc, report_path = self._run_no_llm(tmp_path, monkeypatch)

        assert report_path.exists(), "review-step-broken sentinel not written"

    def test_sentinel_verdict_is_review_step_broken(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        _rc, report_path = self._run_no_llm(tmp_path, monkeypatch)

        data = json.loads(report_path.read_text())
        assert data.get("verdict") == "review-step-broken", (
            f"expected verdict='review-step-broken', got {data.get('verdict')!r}"
        )

    def test_sentinel_has_summary(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        _rc, report_path = self._run_no_llm(tmp_path, monkeypatch)

        data = json.loads(report_path.read_text())
        assert data.get("summary"), "sentinel must have non-empty summary"

    def test_exits_zero_when_llm_unavailable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from atdd.coach.commands import coach_review

        report_path = tmp_path / "review.json"
        monkeypatch.setenv("ATDD_RUNTIME_ROOT", str(tmp_path / ".atdd" / "runtime"))
        monkeypatch.setattr(
            coach_review, "_resolve_pr_commit", lambda _pr: "deadbeef01234567"
        )
        monkeypatch.setattr(
            coach_review, "_get_pr_diff", lambda **_kw: "# fake diff"
        )
        _register_unavailable_llm(monkeypatch)
        monkeypatch.setattr(coach_review, "_print", lambda msg: None)
        monkeypatch.setattr(coach_review, "_print_err", lambda msg: None)

        rc = coach_review.run(
            pr_number=123,
            in_process=True,
            llm="fake-llm",
            report_file=str(report_path),
        )

        assert rc == 0, f"expected exit 0 when LLM unavailable (sentinel path), got {rc}"
        data = json.loads(report_path.read_text())
        assert data.get("verdict") == "review-step-broken", (
            f"expected review-step-broken sentinel on LLM failure, got {data.get('verdict')!r}"
        )
