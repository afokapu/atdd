# URN: test:judge-ambiguous-decisions:judge-and-issue-review:D005-INTEGRATION-001-aggregate-feeds-pre-coach
# Acceptance: acc:judge-ambiguous-decisions:D005-INTEGRATION-001-aggregate-feeds-pre-coach
# WMBT: wmbt:judge-ambiguous-decisions:D005
# Phase: RED
# Layer: integration
"""D005-INTEGRATION-001 — `aggregate.json` feeds the §4.2 pre-coach
precondition: unanimous-pass proceeds; mixed-verdict triggers exactly
one judge call site #5 invocation per #O3; systemic concerns dominate
the aggregate verdict per spec §6.10. With ``--show``, the per-dimension
aggregate verdicts post as a structured GitHub-issue comment.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml


pytestmark = [pytest.mark.platform]


# ---------------------------------------------------------------------------
# Stub helpers
# ---------------------------------------------------------------------------


class _StubClient:
    def __init__(self, payload):
        self._payload = payload

    def invoke(self, prompt: str):
        return self._payload


def _all_pass() -> dict:
    return {
        "dimensions": {
            "systemic":          {"verdict": "pass", "findings": []},
            "ambiguities":       {"verdict": "pass", "findings": []},
            "gap":               {"verdict": "pass", "findings": []},
            "regression":        {"verdict": "pass", "findings": []},
            "comprehensiveness": {"verdict": "pass", "findings": []},
        }
    }


def _concern_in(dimension: str, *, detail: str = "x") -> dict:
    payload = _all_pass()
    payload["dimensions"][dimension] = {
        "verdict": "concern",
        "findings": [{"rule_id": None, "severity": 3, "detail": detail}],
    }
    return payload


def _register(name: str, payload):
    from atdd.coach.commands import judge as judge_mod

    judge_mod.register_llm_client(name, lambda: _StubClient(payload))


@pytest.fixture(autouse=True)
def _reset_registry_and_disable_rule_binding(monkeypatch: pytest.MonkeyPatch):
    from atdd.coach.commands import judge as judge_mod

    snapshot = dict(judge_mod.LLM_REGISTRY)
    judge_mod.LLM_REGISTRY.clear()

    # Avoid coupling these integration tests to the live rule registry —
    # bind_rule() walks every convention file and is irrelevant to the
    # routing-shape contracts we are exercising here.
    from atdd.coach.commands import issue_review as ir

    class _Skip(Exception):
        pass
    monkeypatch.setattr(ir, "bind_rule", lambda r: (_ for _ in ()).throw(_Skip(r)))
    monkeypatch.setattr(ir, "RuleBindingError", _Skip)

    yield
    judge_mod.LLM_REGISTRY.clear()
    judge_mod.LLM_REGISTRY.update(snapshot)


@pytest.fixture
def review_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".atdd").mkdir()
    (tmp_path / ".atdd" / "config.yaml").write_text(yaml.safe_dump({"version": "1.0"}))
    return tmp_path


# ---------------------------------------------------------------------------
# Unanimous-pass: aggregate verdict allows coach to proceed
# ---------------------------------------------------------------------------


class TestUnanimousPassAllowsProceed:
    def test_three_pass_passes_yield_unanimous_pass(self, review_workspace: Path):
        from atdd.coach.commands.issue_review import run, classify_aggregate

        for name in ("haiku", "mini", "flash"):
            _register(name, _all_pass())
        rc = run(
            issue_number=1001,
            passes=3,
            llms=["haiku", "mini", "flash"],
        )
        assert rc == 0

        agg = json.loads(
            (review_workspace / ".atdd" / "runtime" / "issue-reviews" / "1001" / "aggregate.json").read_text()
        )
        assert agg["verdict"] == "unanimous-pass"

        # The §4.2 routing helper agrees this is a "proceed" verdict.
        decision = classify_aggregate(agg)
        assert decision == "proceed"


# ---------------------------------------------------------------------------
# Mixed verdict: triggers exactly one judge call site #5 invocation
# ---------------------------------------------------------------------------


class TestMixedVerdictTriggersJudgeCallSiteFive:
    def test_mixed_verdict_classifies_as_request_judge(self, review_workspace: Path):
        from atdd.coach.commands.issue_review import run, classify_aggregate

        # Pass 1 concerned in `gap`, the others all-pass → disagreement.
        _register("haiku", _concern_in("gap", detail="missing edge case"))
        _register("mini",  _all_pass())
        _register("flash", _all_pass())
        rc = run(
            issue_number=1002,
            passes=3,
            llms=["haiku", "mini", "flash"],
        )
        assert rc == 0

        agg = json.loads(
            (review_workspace / ".atdd" / "runtime" / "issue-reviews" / "1002" / "aggregate.json").read_text()
        )
        assert agg["verdict"] == "mixed-verdict"
        assert classify_aggregate(agg) == "request-judge"

    def test_mixed_verdict_invokes_judge_call_site_five_exactly_once(
        self, review_workspace: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """The pre-coach precondition consumer dispatches one judge call.

        The consumer lives in #O3 (judge call site #5). For this issue, we
        verify that *something* is invoked exactly once at the judge boundary
        when the aggregate is mixed-verdict — the contract O5 owes is "given
        a mixed-verdict aggregate, route to judge once".
        """
        from atdd.coach.commands.issue_review import (
            run, classify_aggregate, route_aggregate_to_judge,
        )

        _register("haiku", _concern_in("ambiguities", detail="ambiguous"))
        _register("mini",  _all_pass())
        _register("flash", _all_pass())
        run(
            issue_number=1003,
            passes=3,
            llms=["haiku", "mini", "flash"],
        )

        agg_path = (
            review_workspace
            / ".atdd" / "runtime" / "issue-reviews" / "1003" / "aggregate.json"
        )
        agg = json.loads(agg_path.read_text())
        assert classify_aggregate(agg) == "request-judge"

        invocations: list[dict] = []

        def _fake_judge(call_site: str, payload: dict) -> dict:
            invocations.append({"call_site": call_site, "payload": payload})
            return {"decision": "request_revision"}

        outcome = route_aggregate_to_judge(agg, judge_fn=_fake_judge)
        assert len(invocations) == 1
        assert invocations[0]["call_site"] == "review-disposition"
        assert outcome["decision"] == "request_revision"

    def test_unanimous_aggregates_do_not_invoke_judge(
        self, review_workspace: Path
    ):
        from atdd.coach.commands.issue_review import (
            run, route_aggregate_to_judge,
        )

        for name in ("haiku", "mini", "flash"):
            _register(name, _all_pass())
        run(
            issue_number=1004,
            passes=3,
            llms=["haiku", "mini", "flash"],
        )
        agg = json.loads(
            (review_workspace / ".atdd" / "runtime" / "issue-reviews" / "1004" / "aggregate.json").read_text()
        )

        invocations: list[dict] = []

        def _fake_judge(call_site: str, payload: dict) -> dict:
            invocations.append({"call_site": call_site, "payload": payload})
            return {"decision": "proceed"}

        outcome = route_aggregate_to_judge(agg, judge_fn=_fake_judge)
        assert invocations == []
        assert outcome["decision"] == "proceed"


# ---------------------------------------------------------------------------
# Systemic concerns dominate per spec §6.10
# ---------------------------------------------------------------------------


class TestSystemicConcernDominates:
    def test_single_systemic_concern_yields_unanimous_concern(
        self, review_workspace: Path
    ):
        from atdd.coach.commands.issue_review import run, classify_aggregate

        # One pass surfaces a systemic concern; the others are all-pass.
        # Per spec §6.10 systemic dominates → aggregate is "unanimous-concern".
        _register("haiku", _concern_in("systemic", detail="structural mismatch"))
        _register("mini",  _all_pass())
        _register("flash", _all_pass())
        rc = run(
            issue_number=1005,
            passes=3,
            llms=["haiku", "mini", "flash"],
        )
        assert rc == 0

        agg = json.loads(
            (review_workspace / ".atdd" / "runtime" / "issue-reviews" / "1005" / "aggregate.json").read_text()
        )
        assert agg["verdict"] == "unanimous-concern"
        assert classify_aggregate(agg) == "block"


# ---------------------------------------------------------------------------
# --show: aggregate posts as a structured GitHub comment
# ---------------------------------------------------------------------------


class TestShowPostsGithubComment:
    def test_show_posts_per_dimension_table_to_github(
        self, review_workspace: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from atdd.coach.commands import issue_review as ir
        from atdd.coach.commands.issue_review import run

        posted: list[dict] = []

        def _fake_post(*, issue_number: int, body: str) -> int:
            posted.append({"issue_number": issue_number, "body": body})
            return 0

        monkeypatch.setattr(ir, "post_issue_comment", _fake_post)

        _register("haiku", _concern_in("regression", detail="API rename without compat shim"))
        _register("mini",  _all_pass())
        _register("flash", _all_pass())
        rc = run(
            issue_number=1006,
            passes=3,
            llms=["haiku", "mini", "flash"],
            show=True,
        )
        assert rc == 0
        assert len(posted) == 1
        assert posted[0]["issue_number"] == 1006
        body = posted[0]["body"]
        # Per spec §6.10 the comment surfaces per-dimension aggregate verdicts.
        for dim in ("systemic", "ambiguities", "gap", "regression", "comprehensiveness"):
            assert dim in body
        assert "regression" in body
        # The finding detail must surface so the issue author can act.
        assert "API rename without compat shim" in body

    def test_show_omitted_does_not_post_to_github(
        self, review_workspace: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from atdd.coach.commands import issue_review as ir
        from atdd.coach.commands.issue_review import run

        posted: list[dict] = []
        monkeypatch.setattr(
            ir, "post_issue_comment",
            lambda *, issue_number, body: posted.append({"i": issue_number}) or 0,
        )
        for name in ("haiku", "mini", "flash"):
            _register(name, _all_pass())
        rc = run(
            issue_number=1007,
            passes=3,
            llms=["haiku", "mini", "flash"],
            show=False,
        )
        assert rc == 0
        assert posted == []
