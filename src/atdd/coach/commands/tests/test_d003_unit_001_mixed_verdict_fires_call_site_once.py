# URN: test:judge-ambiguous-decisions:judge-and-issue-review:D003-UNIT-001-mixed-verdict-fires-call-site-once
# Acceptance: acc:judge-ambiguous-decisions:D003-UNIT-001-mixed-verdict-fires-call-site-once
# WMBT: wmbt:judge-ambiguous-decisions:D003
# Phase: RED
# Layer: unit
"""D003-UNIT-001 — call site #5 (issue review aggregate) trigger discipline.

Per spec §6.9 #5 / §6.10 (and issue #523):

  * unanimous-pass aggregates fire ZERO judge calls (the §4.2 pre-coach
    precondition routes directly to coach-ready).
  * mixed-verdict aggregates fire EXACTLY ONE call to ``atdd judge`` with
    ``--prompt-template judge-issue-review-aggregate.prompt.yaml`` and
    ``--schema judge-issue-review-aggregate.response.schema.json``.
  * Single-pass systemic concerns (one pass flagged ``systemic``, others
    silent) ALSO fire call site #5 — per §6.10 systemic dominates, but
    the disagreement still requires consolidation rather than a flat
    block.
  * judgments.jsonl receives exactly one line per mixed-verdict review
    with ``call_site="issue-review-aggregate"`` (the §6.9 #5 surface).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


pytestmark = [pytest.mark.platform]


# ---------------------------------------------------------------------------
# Aggregate fixtures
# ---------------------------------------------------------------------------


def _passes_meta(n: int) -> list[dict]:
    return [
        {"pass_id": i, "llm": f"llm-{i}", "timestamp": "2026-05-09T12:00:00Z"}
        for i in range(1, n + 1)
    ]


def _all_pass_dims() -> dict:
    return {
        d: {"verdict": "pass", "concern_passes": []}
        for d in ("systemic", "ambiguities", "gap", "regression", "comprehensiveness")
    }


def _agg(verdict: str, *, dims: dict, passes: int = 3, findings=None, issue: int = 1234) -> dict:
    return {
        "issue": issue,
        "generated_at": "2026-05-09T12:00:00Z",
        "passes": _passes_meta(passes),
        "dimensions": dims,
        "verdict": verdict,
        "findings": findings or [],
    }


def _unanimous_pass_aggregate(issue: int = 1234) -> dict:
    return _agg("unanimous-pass", dims=_all_pass_dims(), issue=issue)


def _mixed_verdict_aggregate(issue: int = 1235) -> dict:
    dims = _all_pass_dims()
    dims["gap"] = {"verdict": "concern", "concern_passes": [1]}
    findings = [
        {"pass_id": 1, "llm": "llm-1", "dimension": "gap", "severity": 3, "detail": "missing edge case"}
    ]
    return _agg("mixed-verdict", dims=dims, findings=findings, issue=issue)


def _single_pass_systemic_aggregate(issue: int = 1236) -> dict:
    """One pass flagged systemic concern; others were silent. Per §6.10
    systemic dominates → verdict is `unanimous-concern`, but call site #5
    must still fire to consolidate."""
    dims = _all_pass_dims()
    dims["systemic"] = {"verdict": "concern", "concern_passes": [1]}
    findings = [
        {"pass_id": 1, "llm": "llm-1", "dimension": "systemic", "severity": 4, "detail": "structural mismatch"}
    ]
    return _agg("unanimous-concern", dims=dims, findings=findings, issue=issue)


def _all_concur_concern_aggregate(issue: int = 1237) -> dict:
    """Every pass flagged the same dimension as concern — true unanimous
    concern, no disagreement to consolidate. Should NOT fire call site #5."""
    dims = _all_pass_dims()
    dims["regression"] = {"verdict": "concern", "concern_passes": [1, 2, 3]}
    findings = [
        {"pass_id": i, "llm": f"llm-{i}", "dimension": "regression", "severity": 4, "detail": "same regression"}
        for i in (1, 2, 3)
    ]
    return _agg("unanimous-concern", dims=dims, findings=findings, issue=issue)


# ---------------------------------------------------------------------------
# Workspace fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".atdd").mkdir()
    (tmp_path / ".atdd" / "config.yaml").write_text("version: '1.0'\n")
    return tmp_path


def _stub_judge_response() -> dict:
    return {
        "decision": "request_revision",
        "consolidated_feedback": "Please address the gap finding.",
        "dominant_dimensions": ["gap"],
    }


def _register_stub(payload: dict) -> str:
    """Register a stub LLM client that always returns ``payload``. Returns
    the registered name."""
    from atdd.coach.commands import judge as judge_mod

    class _StubClient:
        def invoke(self, prompt: str):
            return payload

    judge_mod.register_llm_client("stub-d003", lambda: _StubClient())
    return "stub-d003"


@pytest.fixture(autouse=True)
def _isolate_judge_registry():
    from atdd.coach.commands import judge as judge_mod

    snapshot = dict(judge_mod.LLM_REGISTRY)
    judge_mod.LLM_REGISTRY.clear()
    yield
    judge_mod.LLM_REGISTRY.clear()
    judge_mod.LLM_REGISTRY.update(snapshot)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTriggerPredicate:
    """``should_fire_issue_review_aggregate`` honors the §6.10 rules."""

    def test_unanimous_pass_does_not_fire(self):
        from atdd.coach.commands.judge_call_sites import (
            should_fire_issue_review_aggregate,
        )

        assert should_fire_issue_review_aggregate(_unanimous_pass_aggregate()) is False

    def test_mixed_verdict_fires(self):
        from atdd.coach.commands.judge_call_sites import (
            should_fire_issue_review_aggregate,
        )

        assert should_fire_issue_review_aggregate(_mixed_verdict_aggregate()) is True

    def test_single_pass_systemic_concern_fires(self):
        """Per §6.10 systemic dominates → verdict `unanimous-concern`, but
        call site #5 still fires to consolidate."""
        from atdd.coach.commands.judge_call_sites import (
            should_fire_issue_review_aggregate,
        )

        assert (
            should_fire_issue_review_aggregate(_single_pass_systemic_aggregate())
            is True
        )

    def test_all_passes_concur_on_concern_does_not_fire(self):
        """Every pass flagged the same dimension. No disagreement to
        consolidate → block deterministically, no judge call."""
        from atdd.coach.commands.judge_call_sites import (
            should_fire_issue_review_aggregate,
        )

        assert (
            should_fire_issue_review_aggregate(_all_concur_concern_aggregate())
            is False
        )


class TestJudgmentsJsonlReceivesOneLinePerMixedVerdict:
    """``invoke_issue_review_aggregate_judge`` writes exactly one judgments.jsonl
    line with call_site=issue-review-aggregate when the predicate fires."""

    def test_unanimous_pass_writes_zero_judge_lines(self, repo: Path):
        from atdd.coach.commands.judge_call_sites import (
            invoke_issue_review_aggregate_judge,
        )

        llm = _register_stub(_stub_judge_response())
        outcome = invoke_issue_review_aggregate_judge(
            issue_number=1234,
            aggregate=_unanimous_pass_aggregate(1234),
            llm=llm,
        )
        assert outcome["fired"] is False
        log = repo / ".atdd" / "runtime" / "coach" / "judgments.jsonl"
        assert not log.exists() or log.read_text().strip() == ""

    def test_mixed_verdict_writes_exactly_one_judge_line(self, repo: Path):
        from atdd.coach.commands.judge_call_sites import (
            invoke_issue_review_aggregate_judge,
        )

        llm = _register_stub(_stub_judge_response())
        outcome = invoke_issue_review_aggregate_judge(
            issue_number=1235,
            aggregate=_mixed_verdict_aggregate(1235),
            llm=llm,
        )
        assert outcome["fired"] is True
        assert outcome["response"]["decision"] == "request_revision"

        log = repo / ".atdd" / "runtime" / "coach" / "judgments.jsonl"
        lines = [json.loads(ln) for ln in log.read_text().splitlines() if ln.strip()]
        assert len(lines) == 1
        assert lines[0]["call_site"] == "issue-review-aggregate"
        assert lines[0]["outcome"] == "ok"
        assert lines[0]["inputs_hash"]

    def test_single_pass_systemic_writes_one_judge_line(self, repo: Path):
        from atdd.coach.commands.judge_call_sites import (
            invoke_issue_review_aggregate_judge,
        )

        llm = _register_stub(_stub_judge_response())
        outcome = invoke_issue_review_aggregate_judge(
            issue_number=1236,
            aggregate=_single_pass_systemic_aggregate(1236),
            llm=llm,
        )
        assert outcome["fired"] is True

        log = repo / ".atdd" / "runtime" / "coach" / "judgments.jsonl"
        lines = [json.loads(ln) for ln in log.read_text().splitlines() if ln.strip()]
        assert len(lines) == 1
        assert lines[0]["call_site"] == "issue-review-aggregate"

    def test_inputs_hash_stable_across_runs(self, repo: Path):
        """Same (issue_number, aggregate) → same inputs_hash, so re-runs
        on coach --resume are cache-resolvable."""
        from atdd.coach.commands.judge_call_sites import (
            inputs_hash_for_aggregate,
        )

        agg = _mixed_verdict_aggregate(1235)
        h1 = inputs_hash_for_aggregate(issue_number=1235, aggregate=agg)
        h2 = inputs_hash_for_aggregate(issue_number=1235, aggregate=agg)
        assert h1 == h2
        # Different issue → different hash
        h3 = inputs_hash_for_aggregate(issue_number=9999, aggregate=agg)
        assert h1 != h3
