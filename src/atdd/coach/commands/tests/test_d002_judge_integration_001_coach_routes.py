# URN: test:judge-ambiguous-decisions:judge-and-issue-review:D002-INTEGRATION-001-coach-routes-per-response
# Acceptance: acc:judge-ambiguous-decisions:D002-INTEGRATION-001-coach-routes-per-response
# WMBT: wmbt:judge-ambiguous-decisions:D002
# Phase: RED
# Layer: integration
"""D002-INTEGRATION-001 -- coach routes per response for call sites #1, #3, #4.

End-to-end coach run with fixture LLM responses exercising every decision
branch:

  * Call site #1 (borderline tier-1):
    - ``pass``       -> no transition, coach_ready decision
    - ``respawn``    -> triggers spawn-feedback path
    - ``annotate``   -> continues with PR annotation

  * Call site #3 (retry-vs-escalate):
    - ``retry``      -> no transition, coach continues
    - ``escalate``   -> transitions to BLOCKED with operator notification

  * Call site #4 (cross-phase regression):
    - ``fix_in_place``       -> no transition, stays in current phase
    - ``reopen_prior_phase`` -> rolls back to named target phase
    - ``escalate``           -> transitions to BLOCKED

Each ``decisions.jsonl`` entry references the upstream ``judgments.jsonl``
``judgment_id``.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


pytestmark = [pytest.mark.platform]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _register_stub(payload: dict) -> str:
    from atdd.coach.commands import judge as judge_mod

    class _Client:
        def invoke(self, prompt: str):
            return payload

    judge_mod.register_llm_client("stub-d002-int", lambda: _Client())
    return "stub-d002-int"


@pytest.fixture(autouse=True)
def _isolate_judge_registry():
    from atdd.coach.commands import judge as judge_mod

    snapshot = dict(judge_mod.LLM_REGISTRY)
    judge_mod.LLM_REGISTRY.clear()
    yield
    judge_mod.LLM_REGISTRY.clear()
    judge_mod.LLM_REGISTRY.update(snapshot)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".atdd").mkdir()
    (tmp_path / ".atdd" / "config.yaml").write_text("version: '1.0'\n")
    return tmp_path


def _read_decisions(repo_root: Path) -> list[dict]:
    log = repo_root / ".atdd" / "runtime" / "coach" / "decisions.jsonl"
    if not log.exists():
        return []
    return [json.loads(ln) for ln in log.read_text().splitlines() if ln.strip()]


def _read_judgments(repo_root: Path) -> list[dict]:
    log = repo_root / ".atdd" / "runtime" / "coach" / "judgments.jsonl"
    if not log.exists():
        return []
    return [json.loads(ln) for ln in log.read_text().splitlines() if ln.strip()]


def _borderline_context() -> dict:
    return {
        "violations": [
            {"rule_id": "r1", "severity": 2, "disposition": "strict", "location": "a.py:10"},
            {"rule_id": "r2", "severity": 3, "disposition": "strict", "location": "b.py:20"},
        ],
        "total_rules": 3,
        "recently_edited_lines": [],
    }


def _retry_context() -> dict:
    return {"retry_count": 2, "max_retries": 3}


def _regression_context() -> dict:
    return {
        "current_phase": "SMOKE",
        "predecessor_phase": "GREEN",
        "current_violations": [
            {"rule_id": "r-new", "location": "c.py:30"},
        ],
        "predecessor_exit_violations": [],
    }


# ---------------------------------------------------------------------------
# Call site #1 -- borderline tier-1 routing
# ---------------------------------------------------------------------------


class TestBorderlineTier1PassBranch:
    def test_pass_emits_coach_ready_referencing_judgment(self, repo: Path):
        from atdd.coach.commands.judge_call_sites import route_borderline_tier1

        llm = _register_stub({
            "decision": "pass",
            "confidence": 0.85,
            "rationale": "violations are advisory-level, not blocking",
        })
        outcome = route_borderline_tier1(
            context=_borderline_context(),
            llm=llm,
            coach_run_id="run-bt1-pass",
        )
        assert outcome["decision"] == "pass"
        decisions = _read_decisions(repo)
        ready = [d for d in decisions if d["decision_type"] == "coach_ready"]
        assert len(ready) == 1
        judgments = _read_judgments(repo)
        assert len(judgments) == 1
        assert ready[0]["judgment_id"] == judgments[0]["judgment_id"]


class TestBorderlineTier1RespawnBranch:
    def test_respawn_triggers_spawn_feedback(self, repo: Path):
        from atdd.coach.commands.judge_call_sites import route_borderline_tier1

        llm = _register_stub({
            "decision": "respawn",
            "confidence": 0.6,
            "rationale": "mixed signals suggest migration in flight",
        })
        outcome = route_borderline_tier1(
            context=_borderline_context(),
            llm=llm,
            coach_run_id="run-bt1-respawn",
        )
        assert outcome["decision"] == "respawn"
        decisions = _read_decisions(repo)
        spawn_decisions = [d for d in decisions if d["decision_type"] == "spawn_feedback"]
        assert len(spawn_decisions) == 1
        judgments = _read_judgments(repo)
        assert spawn_decisions[0]["judgment_id"] == judgments[0]["judgment_id"]


class TestBorderlineTier1AnnotateBranch:
    def test_annotate_posts_pr_annotation_with_rationale(self, repo: Path):
        from atdd.coach.commands import judge_call_sites as cs
        from atdd.coach.commands.judge_call_sites import route_borderline_tier1

        annotations: list[dict] = []

        def _fake_annotate(*, rationale: str, **kwargs) -> int:
            annotations.append({"rationale": rationale})
            return 0

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(cs, "post_pr_annotation", _fake_annotate)

        try:
            rationale = "suppress-and-clean cluster near migration edit; annotate for review"
            llm = _register_stub({
                "decision": "annotate",
                "confidence": 0.72,
                "rationale": rationale,
            })
            outcome = route_borderline_tier1(
                context=_borderline_context(),
                llm=llm,
                coach_run_id="run-bt1-annotate",
            )
            assert outcome["decision"] == "annotate"
            assert len(annotations) == 1
            assert rationale in annotations[0]["rationale"]
            decisions = _read_decisions(repo)
            ann = [d for d in decisions if d["decision_type"] == "pr_annotation"]
            assert len(ann) == 1
            judgments = _read_judgments(repo)
            assert ann[0]["judgment_id"] == judgments[0]["judgment_id"]
        finally:
            monkeypatch.undo()


# ---------------------------------------------------------------------------
# Call site #3 -- retry-vs-escalate routing
# ---------------------------------------------------------------------------


class TestRetryVsEscalateRetryBranch:
    def test_retry_emits_continue_decision(self, repo: Path):
        from atdd.coach.commands.judge_call_sites import route_retry_vs_escalate

        llm = _register_stub({
            "decision": "retry",
            "reasoning": "previous failure was transient; one more attempt likely to succeed",
        })
        outcome = route_retry_vs_escalate(
            context=_retry_context(),
            llm=llm,
            coach_run_id="run-rve-retry",
        )
        assert outcome["decision"] == "retry"
        assert outcome["state"] == "CONTINUE"
        decisions = _read_decisions(repo)
        cont = [d for d in decisions if d["decision_type"] == "continue"]
        assert len(cont) == 1
        judgments = _read_judgments(repo)
        assert cont[0]["judgment_id"] == judgments[0]["judgment_id"]


class TestRetryVsEscalateEscalateBranch:
    def test_escalate_transitions_to_blocked(self, repo: Path):
        from atdd.coach.commands import judge_call_sites as cs
        from atdd.coach.commands.judge_call_sites import route_retry_vs_escalate

        notifications: list[dict] = []

        def _fake_notify(*, issue_number: int, rationale: str) -> int:
            notifications.append({"issue_number": issue_number, "rationale": rationale})
            return 0

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(cs, "notify_operator_blocked", _fake_notify)

        try:
            reasoning = "repeated transient failure suggests infra issue; operator intervention needed"
            llm = _register_stub({
                "decision": "escalate",
                "reasoning": reasoning,
            })
            outcome = route_retry_vs_escalate(
                context=_retry_context(),
                llm=llm,
                coach_run_id="run-rve-escalate",
            )
            assert outcome["decision"] == "escalate"
            assert outcome["state"] == "BLOCKED"
            assert len(notifications) == 1
            decisions = _read_decisions(repo)
            esc = [d for d in decisions if d["decision_type"] == "escalation"]
            assert len(esc) == 1
            judgments = _read_judgments(repo)
            assert esc[0]["judgment_id"] == judgments[0]["judgment_id"]
        finally:
            monkeypatch.undo()


# ---------------------------------------------------------------------------
# Call site #4 -- cross-phase regression routing
# ---------------------------------------------------------------------------


class TestCrossPhaseRegressionFixInPlaceBranch:
    def test_fix_in_place_stays_in_current_phase(self, repo: Path):
        from atdd.coach.commands.judge_call_sites import route_cross_phase_regression

        llm = _register_stub({
            "decision": "fix_in_place",
            "target_phase": "SMOKE",
            "rationale": "regression is a missing import; fixable without rollback",
        })
        outcome = route_cross_phase_regression(
            context=_regression_context(),
            llm=llm,
            coach_run_id="run-cpr-fix",
        )
        assert outcome["decision"] == "fix_in_place"
        assert outcome["state"] == "CONTINUE"
        decisions = _read_decisions(repo)
        cont = [d for d in decisions if d["decision_type"] == "continue"]
        assert len(cont) == 1
        judgments = _read_judgments(repo)
        assert cont[0]["judgment_id"] == judgments[0]["judgment_id"]


class TestCrossPhaseRegressionReopenPriorPhaseBranch:
    def test_reopen_prior_phase_rolls_back(self, repo: Path):
        from atdd.coach.commands.judge_call_sites import route_cross_phase_regression

        llm = _register_stub({
            "decision": "reopen_prior_phase",
            "target_phase": "GREEN",
            "rationale": "regression invalidates GREEN exit claims; must re-green",
        })
        outcome = route_cross_phase_regression(
            context=_regression_context(),
            llm=llm,
            coach_run_id="run-cpr-reopen",
        )
        assert outcome["decision"] == "reopen_prior_phase"
        assert outcome["target_phase"] == "GREEN"
        decisions = _read_decisions(repo)
        rollback = [d for d in decisions if d["decision_type"] == "phase_rollback"]
        assert len(rollback) == 1
        assert rollback[0]["outcome"]["target_phase"] == "GREEN"
        judgments = _read_judgments(repo)
        assert rollback[0]["judgment_id"] == judgments[0]["judgment_id"]


class TestCrossPhaseRegressionEscalateBranch:
    def test_escalate_transitions_to_blocked(self, repo: Path):
        from atdd.coach.commands import judge_call_sites as cs
        from atdd.coach.commands.judge_call_sites import route_cross_phase_regression

        notifications: list[dict] = []

        def _fake_notify(*, issue_number: int, rationale: str) -> int:
            notifications.append({"issue_number": issue_number, "rationale": rationale})
            return 0

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(cs, "notify_operator_blocked", _fake_notify)

        try:
            rationale = "cross-phase regression with no clear fix; operator must assess"
            llm = _register_stub({
                "decision": "escalate",
                "target_phase": "GREEN",
                "rationale": rationale,
            })
            outcome = route_cross_phase_regression(
                context=_regression_context(),
                llm=llm,
                coach_run_id="run-cpr-escalate",
            )
            assert outcome["decision"] == "escalate"
            assert outcome["state"] == "BLOCKED"
            assert len(notifications) == 1
            decisions = _read_decisions(repo)
            esc = [d for d in decisions if d["decision_type"] == "escalation"]
            assert len(esc) == 1
            judgments = _read_judgments(repo)
            assert esc[0]["judgment_id"] == judgments[0]["judgment_id"]
        finally:
            monkeypatch.undo()
