# URN: test:judge-ambiguous-decisions:judge-and-issue-review:D003-INTEGRATION-001-coach-routes-aggregate-decision
# Acceptance: acc:judge-ambiguous-decisions:D003-INTEGRATION-001-coach-routes-aggregate-decision
# WMBT: wmbt:judge-ambiguous-decisions:D003
# Phase: RED
# Layer: integration
"""D003-INTEGRATION-001 — coach routes the aggregate decision per spec §6.9 #5.

End-to-end pre-coach run with a fixture aggregate.json and a stub LLM
returning each of the three decision branches:

  * ``accept``           → emits a ``coach_ready`` decision in
                           ``decisions.jsonl`` referencing the
                           ``judgment_id``.
  * ``request_revision`` → posts the ``consolidated_feedback`` as a
                           GitHub comment on the issue and emits a
                           ``pre_coach_paused`` decision.
  * ``escalate``         → transitions issue state to BLOCKED with the
                           rationale visible in the operator notification.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


pytestmark = [pytest.mark.platform]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _aggregate(issue: int) -> dict:
    """A mixed-verdict aggregate so the trigger predicate fires."""
    dims = {
        d: {"verdict": "pass", "concern_passes": []}
        for d in ("systemic", "ambiguities", "gap", "regression", "comprehensiveness")
    }
    dims["gap"] = {"verdict": "concern", "concern_passes": [1]}
    return {
        "issue": issue,
        "generated_at": "2026-05-09T12:00:00Z",
        "passes": [
            {"pass_id": 1, "llm": "haiku", "timestamp": "2026-05-09T12:00:00Z"},
            {"pass_id": 2, "llm": "mini",  "timestamp": "2026-05-09T12:00:01Z"},
            {"pass_id": 3, "llm": "flash", "timestamp": "2026-05-09T12:00:02Z"},
        ],
        "dimensions": dims,
        "verdict": "mixed-verdict",
        "findings": [
            {
                "pass_id": 1, "llm": "haiku", "dimension": "gap",
                "severity": 3, "detail": "missing edge case for empty input",
            }
        ],
    }


def _register_stub(payload: dict) -> str:
    from atdd.coach.commands import judge as judge_mod

    class _Client:
        def invoke(self, prompt: str):
            return payload

    judge_mod.register_llm_client("stub-d003-int", lambda: _Client())
    return "stub-d003-int"


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


# ---------------------------------------------------------------------------
# Branch: accept
# ---------------------------------------------------------------------------


class TestAcceptBranch:
    def test_accept_emits_coach_ready_decision_referencing_judgment_id(
        self, repo: Path
    ):
        from atdd.coach.commands.judge_call_sites import (
            route_issue_review_aggregate,
        )

        llm = _register_stub({
            "decision": "accept",
            "consolidated_feedback": "All passes consolidate to acceptable.",
            "dominant_dimensions": ["gap"],
        })
        outcome = route_issue_review_aggregate(
            issue_number=2001,
            aggregate=_aggregate(2001),
            llm=llm,
            coach_run_id="run-2001",
        )

        assert outcome["decision"] == "accept"
        decisions = _read_decisions(repo)
        ready = [d for d in decisions if d["decision_type"] == "coach_ready"]
        assert len(ready) == 1, decisions

        judgments = _read_judgments(repo)
        assert len(judgments) == 1
        # decisions.jsonl entry references the judgments.jsonl entry
        assert ready[0]["judgment_id"] == judgments[0]["judgment_id"]
        assert ready[0]["issue_number"] == 2001


# ---------------------------------------------------------------------------
# Branch: request_revision
# ---------------------------------------------------------------------------


class TestRequestRevisionBranch:
    def test_request_revision_posts_comment_and_emits_paused_decision(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from atdd.coach.commands import judge_call_sites as cs
        from atdd.coach.commands.judge_call_sites import (
            route_issue_review_aggregate,
        )

        posted: list[dict] = []

        def _fake_post(*, issue_number: int, body: str) -> int:
            posted.append({"issue_number": issue_number, "body": body})
            return 0

        monkeypatch.setattr(cs, "post_issue_comment", _fake_post)

        feedback = "Please address the missing edge case for empty input."
        llm = _register_stub({
            "decision": "request_revision",
            "consolidated_feedback": feedback,
            "dominant_dimensions": ["gap"],
        })

        outcome = route_issue_review_aggregate(
            issue_number=2002,
            aggregate=_aggregate(2002),
            llm=llm,
            coach_run_id="run-2002",
        )

        assert outcome["decision"] == "request_revision"
        # Comment posted on the *issue*, not a PR.
        assert len(posted) == 1
        assert posted[0]["issue_number"] == 2002
        assert feedback in posted[0]["body"]

        decisions = _read_decisions(repo)
        paused = [d for d in decisions if d["decision_type"] == "pre_coach_paused"]
        assert len(paused) == 1
        judgments = _read_judgments(repo)
        assert paused[0]["judgment_id"] == judgments[0]["judgment_id"]


# ---------------------------------------------------------------------------
# Branch: escalate
# ---------------------------------------------------------------------------


class TestEscalateBranch:
    def test_escalate_transitions_to_blocked_with_rationale(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from atdd.coach.commands import judge_call_sites as cs
        from atdd.coach.commands.judge_call_sites import (
            route_issue_review_aggregate,
        )

        notifications: list[dict] = []

        def _fake_notify(*, issue_number: int, rationale: str) -> int:
            notifications.append({"issue_number": issue_number, "rationale": rationale})
            return 0

        monkeypatch.setattr(cs, "notify_operator_blocked", _fake_notify)

        rationale = "Systemic mismatch — operator review required before coach proceeds."
        llm = _register_stub({
            "decision": "escalate",
            "consolidated_feedback": rationale,
            "dominant_dimensions": ["systemic"],
        })

        outcome = route_issue_review_aggregate(
            issue_number=2003,
            aggregate=_aggregate(2003),
            llm=llm,
            coach_run_id="run-2003",
        )

        assert outcome["decision"] == "escalate"
        assert outcome["state"] == "BLOCKED"

        # Operator sees the rationale.
        assert len(notifications) == 1
        assert notifications[0]["issue_number"] == 2003
        assert rationale in notifications[0]["rationale"]

        decisions = _read_decisions(repo)
        escalations = [d for d in decisions if d["decision_type"] == "escalation"]
        assert len(escalations) == 1
        assert escalations[0]["outcome"]["state"] == "BLOCKED"
        # Rationale is captured in the durable decision record.
        assert rationale in (escalations[0].get("rationale") or "")
        judgments = _read_judgments(repo)
        assert escalations[0]["judgment_id"] == judgments[0]["judgment_id"]


# ---------------------------------------------------------------------------
# Branch: unanimous-pass short-circuits judge entirely
# ---------------------------------------------------------------------------


class TestUnanimousPassShortCircuits:
    def test_unanimous_pass_emits_coach_ready_without_invoking_judge(
        self, repo: Path
    ):
        from atdd.coach.commands.judge_call_sites import (
            route_issue_review_aggregate,
        )

        # Stub registered but should NOT be invoked.
        invoked = {"count": 0}

        from atdd.coach.commands import judge as judge_mod

        class _Client:
            def invoke(self, prompt: str):
                invoked["count"] += 1
                return {
                    "decision": "accept",
                    "consolidated_feedback": "should-not-be-called",
                    "dominant_dimensions": ["gap"],
                }

        judge_mod.register_llm_client("stub-no-call", lambda: _Client())

        agg = {
            "issue": 2004,
            "generated_at": "2026-05-09T12:00:00Z",
            "passes": [
                {"pass_id": 1, "llm": "haiku", "timestamp": "2026-05-09T12:00:00Z"},
                {"pass_id": 2, "llm": "mini",  "timestamp": "2026-05-09T12:00:01Z"},
            ],
            "dimensions": {
                d: {"verdict": "pass", "concern_passes": []}
                for d in ("systemic", "ambiguities", "gap", "regression", "comprehensiveness")
            },
            "verdict": "unanimous-pass",
            "findings": [],
        }

        outcome = route_issue_review_aggregate(
            issue_number=2004,
            aggregate=agg,
            llm="stub-no-call",
            coach_run_id="run-2004",
        )

        assert outcome["decision"] == "accept"
        assert outcome["fired"] is False
        assert invoked["count"] == 0
        # No judgment row, since judge wasn't invoked.
        assert _read_judgments(repo) == []
        decisions = _read_decisions(repo)
        ready = [d for d in decisions if d["decision_type"] == "coach_ready"]
        assert len(ready) == 1
        # judgment_id field absent (None) when the deterministic short-circuit ran.
        assert ready[0].get("judgment_id") is None
