# URN: test:integration-hardening:N5-INTEGRATION-002-verdict-routing
# Acceptance: acc:integration-hardening:N5-INTEGRATION-002-verdict-routing
# Phase: RED
# Layer: unit
"""N5-INTEGRATION-002 — verdict routing: pass/concern/fail.

pass     → HandlerResult.HANDLED (state advances)
concern  → judge call site #2 invoked, then HandlerResult.HANDLED
fail     → HandlerResult.ERROR (triggers respawn)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pytest

pytestmark = [pytest.mark.platform]


def _report(verdict: str, phase: str = "GREEN") -> dict:
    base = {
        "review_id": f"rev-{verdict}-{phase.lower()}",
        "target_commit": "abc123456",
        "reviewer_agent_id": "reviewer-v9-test",
        "wmbt_urn": "wmbt:integration-hardening:N5",
        "phase": phase,
        "verdict": verdict,
        "tier1_risk_score": 0 if verdict == "pass" else 5,
        "findings": [],
        "ac_coverage": {},
        "summary": f"Verdict: {verdict}",
        "recommendations": [],
    }
    if verdict == "concern":
        base["findings"] = [
            {
                "rule_id": None,
                "severity": 2,
                "surface": "semantic",
                "location": "src/x.py",
                "acceptance_ref": "acc:integration-hardening:N5-INTEGRATION-002-verdict-routing",
                "description": "Minor concern.",
                "evidence": "Evidence here.",
            }
        ]
    elif verdict == "fail":
        base["findings"] = [
            {
                "rule_id": None,
                "severity": 5,
                "surface": "architecture",
                "location": "src/y.py",
                "acceptance_ref": "acc:integration-hardening:N5-INTEGRATION-002-verdict-routing",
                "description": "Critical failure.",
                "evidence": "Evidence here.",
            }
        ]
    return base


@pytest.fixture()
def runtime_root(tmp_path: Path) -> Path:
    root = tmp_path / ".atdd" / "runtime"
    root.mkdir(parents=True)
    return root


def _make_ctx(review_phases=None, issue_number: int = 589):
    from atdd.coach.handlers.state_machine import CoachContext

    return CoachContext(
        issue_number=issue_number,
        review_phases=review_phases or {"green"},
    )


def _noop_spawn(ctx, transition, reviewer_agent_id, runtime_root_path):
    pass


class TestVerdictRouting:
    """pass/concern/fail verdicts route correctly."""

    def test_pass_verdict_returns_handled(
        self,
        runtime_root: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setenv("ATDD_RUNTIME_ROOT", str(runtime_root))

        from atdd.coach.handlers import reviewer as rev_handler
        monkeypatch.setattr(rev_handler, "_spawn_reviewer", _noop_spawn)
        monkeypatch.setattr(
            rev_handler,
            "_wait_for_review_report",
            lambda *a, **kw: _report("pass"),
        )

        from atdd.coach.handlers.state_machine import HandlerResult, Phase, Transition

        ctx = _make_ctx(review_phases={"green"})
        result = rev_handler.handle(ctx, Transition(src=Phase.RED, dst=Phase.GREEN))

        assert result == HandlerResult.HANDLED

    def test_fail_verdict_returns_error(
        self,
        runtime_root: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setenv("ATDD_RUNTIME_ROOT", str(runtime_root))

        from atdd.coach.handlers import reviewer as rev_handler
        monkeypatch.setattr(rev_handler, "_spawn_reviewer", _noop_spawn)
        monkeypatch.setattr(
            rev_handler,
            "_wait_for_review_report",
            lambda *a, **kw: _report("fail"),
        )

        from atdd.coach.handlers.state_machine import HandlerResult, Phase, Transition

        ctx = _make_ctx(review_phases={"green"})
        result = rev_handler.handle(ctx, Transition(src=Phase.RED, dst=Phase.GREEN))

        assert result == HandlerResult.ERROR

    def test_concern_verdict_invokes_judge_and_returns_handled(
        self,
        runtime_root: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setenv("ATDD_RUNTIME_ROOT", str(runtime_root))

        judge_calls: list[dict] = []

        from atdd.coach.handlers import reviewer as rev_handler
        monkeypatch.setattr(rev_handler, "_spawn_reviewer", _noop_spawn)
        monkeypatch.setattr(
            rev_handler,
            "_wait_for_review_report",
            lambda *a, **kw: _report("concern"),
        )
        monkeypatch.setattr(
            rev_handler,
            "_route_concern",
            lambda ctx, report: judge_calls.append({"ctx": ctx, "report": report}),
        )

        from atdd.coach.handlers.state_machine import HandlerResult, Phase, Transition

        ctx = _make_ctx(review_phases={"green"})
        result = rev_handler.handle(ctx, Transition(src=Phase.RED, dst=Phase.GREEN))

        assert result == HandlerResult.HANDLED
        assert len(judge_calls) == 1, "Judge call site #2 must be invoked exactly once for concern"

    def test_timeout_returns_error(
        self,
        runtime_root: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setenv("ATDD_RUNTIME_ROOT", str(runtime_root))

        from atdd.coach.handlers import reviewer as rev_handler
        monkeypatch.setattr(rev_handler, "_spawn_reviewer", _noop_spawn)
        monkeypatch.setattr(
            rev_handler,
            "_wait_for_review_report",
            lambda *a, **kw: None,  # timeout: no report
        )

        from atdd.coach.handlers.state_machine import HandlerResult, Phase, Transition

        ctx = _make_ctx(review_phases={"green"})
        result = rev_handler.handle(ctx, Transition(src=Phase.RED, dst=Phase.GREEN))

        assert result == HandlerResult.ERROR
