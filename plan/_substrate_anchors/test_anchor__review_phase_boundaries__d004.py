# URN: test:review-phase-boundaries:d004-unit-001-judge-reviewer-concern-schema
# URN: test:review-phase-boundaries:d004-integration-001-concern-triggers-judge
# URN: test:review-phase-boundaries:d004-integration-002-judgment-jsonl
# Acceptance: acc:review-phase-boundaries:D004-UNIT-001-judge-reviewer-concern-schema-committed
# Acceptance: acc:review-phase-boundaries:D004-INTEGRATION-001-concern-triggers-exactly-one-judge-call
# Acceptance: acc:review-phase-boundaries:D004-INTEGRATION-002-judgment-logged-to-jsonl
# WMBT: wmbt:review-phase-boundaries:D004
# Phase: RED
# Layer: unit / integration
# Runtime: python

"""D004 — judge call site #2 (reviewer concern verdict).

Per spec §6.9 call site #2 / issue #529:

  * When a reviewer returns verdict=concern, coach invokes judge exactly
    once against judge-reviewer-concern.response.schema.json.
  * decision=block → respawn the phase agent with reviewer findings.
  * decision=annotate_and_continue → proceed with pr_annotation queued.
  * Every judgment appends one line to judgments.jsonl BEFORE routing.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest


pytestmark = [pytest.mark.platform]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]

_SCHEMA_PATH = (
    _REPO_ROOT
    / "src" / "atdd" / "coach" / "schemas" / "judge-reviewer-concern.response.schema.json"
)

_FIXTURE_DIR = (
    _REPO_ROOT
    / "src" / "atdd" / "coach" / "schemas" / "fixtures" / "judge-reviewer-concern"
)


def _concern_report(**overrides) -> dict:
    base = {
        "review_id": "rev-concern-d004",
        "target_commit": "deadbeef",
        "reviewer_agent_id": "reviewer-v9-no-write",
        "wmbt_urn": "wmbt:review-phase-boundaries:D004",
        "phase": "GREEN",
        "verdict": "concern",
        "tier1_risk_score": 5,
        "findings": [
            {
                "rule_id": None,
                "severity": 2,
                "surface": "semantic",
                "location": "src/atdd/coach/schemas/review-report.schema.json",
                "acceptance_ref": "acc:review-phase-boundaries:D002-UNIT-004-rule-id-severity-matches-registry",
                "description": "Partial coverage.",
                "evidence": "One AC partially covered.",
            }
        ],
        "ac_coverage": {
            "acc:review-phase-boundaries:D002-UNIT-001-review-report-schema-committed": "covered",
            "acc:review-phase-boundaries:D002-UNIT-004-rule-id-severity-matches-registry": "partial",
        },
        "summary": "Partial coverage; low-severity semantic concern.",
        "recommendations": ["Address the partial coverage."],
    }
    base.update(overrides)
    return base


def _pass_report(**overrides) -> dict:
    base = _concern_report(verdict="pass")
    base["ac_coverage"] = {
        "acc:review-phase-boundaries:D002-UNIT-001-review-report-schema-committed": "covered",
        "acc:review-phase-boundaries:D002-UNIT-004-rule-id-severity-matches-registry": "covered",
    }
    base["findings"] = []
    base["summary"] = "All covered."
    base["recommendations"] = []
    base["tier1_risk_score"] = 0
    base.update(overrides)
    return base


def _fail_report(**overrides) -> dict:
    base = _concern_report(verdict="fail")
    base.update(overrides)
    return base


def _block_response() -> dict:
    return json.loads((_FIXTURE_DIR / "block.json").read_text())


def _annotate_response() -> dict:
    return json.loads((_FIXTURE_DIR / "annotate_and_continue.json").read_text())


def _register_stub(payload: dict) -> str:
    from atdd.coach.commands import judge as judge_mod

    class _StubClient:
        def invoke(self, prompt: str):
            return payload

    judge_mod.register_llm_client("stub-d004", lambda: _StubClient())
    return "stub-d004"


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".atdd").mkdir()
    (tmp_path / ".atdd" / "config.yaml").write_text("version: '1.0'\n")
    return tmp_path


@pytest.fixture(autouse=True)
def _isolate_judge_registry():
    from atdd.coach.commands import judge as judge_mod

    snapshot = dict(judge_mod.LLM_REGISTRY)
    judge_mod.LLM_REGISTRY.clear()
    yield
    judge_mod.LLM_REGISTRY.clear()
    judge_mod.LLM_REGISTRY.update(snapshot)


# ---------------------------------------------------------------------------
# AC-UNIT-001: Schema validation
# ---------------------------------------------------------------------------


class TestReviewerConcernResponseSchema:
    """judge-reviewer-concern.response.schema.json is valid draft-2020-12
    with required fields decision, rationale, pr_annotation."""

    def test_schema_parses_as_draft_2020_12(self):
        doc = json.loads(_SCHEMA_PATH.read_text())
        assert doc["$schema"] == "https://json-schema.org/draft/2020-12/schema"

    def test_required_fields(self):
        doc = json.loads(_SCHEMA_PATH.read_text())
        assert set(doc["required"]) == {"decision", "rationale", "pr_annotation"}

    def test_decision_enum(self):
        doc = json.loads(_SCHEMA_PATH.read_text())
        assert set(doc["properties"]["decision"]["enum"]) == {
            "block",
            "annotate_and_continue",
        }

    def test_rationale_non_empty(self):
        doc = json.loads(_SCHEMA_PATH.read_text())
        assert doc["properties"]["rationale"]["minLength"] == 1

    def test_pr_annotation_is_string(self):
        doc = json.loads(_SCHEMA_PATH.read_text())
        assert doc["properties"]["pr_annotation"]["type"] == "string"

    def test_block_fixture_validates(self):
        doc = json.loads(_SCHEMA_PATH.read_text())
        validator = jsonschema.Draft202012Validator(doc)
        validator.validate(_block_response())

    def test_annotate_fixture_validates(self):
        doc = json.loads(_SCHEMA_PATH.read_text())
        validator = jsonschema.Draft202012Validator(doc)
        validator.validate(_annotate_response())

    def test_malformed_fixture_fails_validation(self):
        doc = json.loads(_SCHEMA_PATH.read_text())
        validator = jsonschema.Draft202012Validator(doc)
        bad = json.loads((_FIXTURE_DIR / "malformed.json").read_text())
        with pytest.raises(jsonschema.ValidationError):
            validator.validate(bad)

    def test_additional_properties_rejected(self):
        doc = json.loads(_SCHEMA_PATH.read_text())
        validator = jsonschema.Draft202012Validator(doc)
        with pytest.raises(jsonschema.ValidationError):
            validator.validate({
                "decision": "block",
                "rationale": "ok",
                "pr_annotation": "",
                "extra": True,
            })


# ---------------------------------------------------------------------------
# AC-INTEGRATION-001: concern triggers exactly one judge call
# ---------------------------------------------------------------------------


class TestTriggerPredicate:
    """``should_fire_reviewer_concern`` fires only on verdict=concern."""

    def test_concern_verdict_fires(self):
        from atdd.coach.commands.judge_call_sites import (
            should_fire_reviewer_concern,
        )

        assert should_fire_reviewer_concern(_concern_report()) is True

    def test_pass_verdict_does_not_fire(self):
        from atdd.coach.commands.judge_call_sites import (
            should_fire_reviewer_concern,
        )

        assert should_fire_reviewer_concern(_pass_report()) is False

    def test_fail_verdict_does_not_fire(self):
        from atdd.coach.commands.judge_call_sites import (
            should_fire_reviewer_concern,
        )

        assert should_fire_reviewer_concern(_fail_report()) is False


class TestInvokeExactlyOnce:
    """``invoke_reviewer_concern_judge`` calls LLM exactly once when
    verdict=concern and returns the validated response."""

    def test_concern_fires_and_returns_response(self, repo: Path):
        from atdd.coach.commands.judge_call_sites import (
            invoke_reviewer_concern_judge,
        )

        llm = _register_stub(_block_response())
        result = invoke_reviewer_concern_judge(
            review_report=_concern_report(),
            llm=llm,
        )
        assert result["fired"] is True
        assert result["response"]["decision"] == "block"
        assert result["outcome"] == "ok"

    def test_pass_does_not_fire(self, repo: Path):
        from atdd.coach.commands.judge_call_sites import (
            invoke_reviewer_concern_judge,
        )

        llm = _register_stub(_block_response())
        result = invoke_reviewer_concern_judge(
            review_report=_pass_report(),
            llm=llm,
        )
        assert result["fired"] is False

    def test_schema_violation_returns_response_anyway(self, repo: Path):
        from atdd.coach.commands.judge_call_sites import (
            invoke_reviewer_concern_judge,
        )

        bad_payload = {"decision": "invalid", "rationale": "", "pr_annotation": ""}
        llm = _register_stub(bad_payload)
        result = invoke_reviewer_concern_judge(
            review_report=_concern_report(),
            llm=llm,
        )
        assert result["fired"] is True
        assert result["outcome"] == "schema_violation"


class TestRouting:
    """``route_reviewer_concern`` branches correctly on decision."""

    def test_block_routes_to_respawn(self, repo: Path):
        from atdd.coach.commands.judge_call_sites import (
            route_reviewer_concern,
        )

        llm = _register_stub(_block_response())
        result = route_reviewer_concern(
            review_report=_concern_report(),
            llm=llm,
            coach_run_id="run-d004",
        )
        assert result["decision"] == "block"
        assert result["state"] == "RESPAWN"

    def test_annotate_routes_to_continue(self, repo: Path):
        from atdd.coach.commands.judge_call_sites import (
            route_reviewer_concern,
        )

        llm = _register_stub(_annotate_response())
        result = route_reviewer_concern(
            review_report=_concern_report(),
            llm=llm,
            coach_run_id="run-d004",
        )
        assert result["decision"] == "annotate_and_continue"
        assert result["state"] == "CONTINUE"
        assert result["pr_annotation"] != ""

    def test_non_firing_returns_proceed(self, repo: Path):
        from atdd.coach.commands.judge_call_sites import (
            route_reviewer_concern,
        )

        llm = _register_stub(_block_response())
        result = route_reviewer_concern(
            review_report=_pass_report(),
            llm=llm,
            coach_run_id="run-d004",
        )
        assert result["fired"] is False
        assert result["state"] == "PROCEED"


# ---------------------------------------------------------------------------
# AC-INTEGRATION-002: judgment logged to JSONL before routing
# ---------------------------------------------------------------------------


class TestJudgmentLoggedToJsonl:
    """Every call-site-2 judgment appends one line to judgments.jsonl
    BEFORE the routing action runs (spec §4.5)."""

    def test_concern_writes_exactly_one_judgment_line(self, repo: Path):
        from atdd.coach.commands.judge_call_sites import (
            invoke_reviewer_concern_judge,
        )

        llm = _register_stub(_block_response())
        invoke_reviewer_concern_judge(
            review_report=_concern_report(),
            llm=llm,
        )
        log = repo / ".atdd" / "runtime" / "coach" / "judgments.jsonl"
        lines = [json.loads(ln) for ln in log.read_text().splitlines() if ln.strip()]
        assert len(lines) == 1
        assert lines[0]["call_site"] == "reviewer_concern"
        assert lines[0]["outcome"] == "ok"
        assert lines[0]["inputs_hash"]

    def test_judgment_line_has_required_fields(self, repo: Path):
        from atdd.coach.commands.judge_call_sites import (
            invoke_reviewer_concern_judge,
        )

        llm = _register_stub(_annotate_response())
        invoke_reviewer_concern_judge(
            review_report=_concern_report(),
            llm=llm,
        )
        log = repo / ".atdd" / "runtime" / "coach" / "judgments.jsonl"
        line = json.loads(log.read_text().strip())
        for field in ("judgment_id", "timestamp", "call_site", "inputs_hash",
                       "response", "cached", "outcome"):
            assert field in line, f"Missing field: {field}"
        assert line["call_site"] == "reviewer_concern"
        assert line["response"]["decision"] == "annotate_and_continue"

    def test_judgment_written_before_routing_action(self, repo: Path):
        """The judgment line exists in JSONL before route_reviewer_concern
        writes its decision record (durable-decision-before-action)."""
        from atdd.coach.commands.judge_call_sites import (
            route_reviewer_concern,
        )

        llm = _register_stub(_block_response())
        route_reviewer_concern(
            review_report=_concern_report(),
            llm=llm,
            coach_run_id="run-d004-durability",
        )
        log = repo / ".atdd" / "runtime" / "coach" / "judgments.jsonl"
        decisions = repo / ".atdd" / "runtime" / "coach" / "decisions.jsonl"
        j_lines = [json.loads(ln) for ln in log.read_text().splitlines() if ln.strip()]
        d_lines = [json.loads(ln) for ln in decisions.read_text().splitlines() if ln.strip()]
        assert len(j_lines) >= 1
        assert len(d_lines) >= 1
        # Judgment timestamp must be <= decision timestamp
        assert j_lines[0]["timestamp"] <= d_lines[0]["timestamp"]

    def test_no_judgment_line_when_predicate_does_not_fire(self, repo: Path):
        from atdd.coach.commands.judge_call_sites import (
            invoke_reviewer_concern_judge,
        )

        llm = _register_stub(_block_response())
        invoke_reviewer_concern_judge(
            review_report=_pass_report(),
            llm=llm,
        )
        log = repo / ".atdd" / "runtime" / "coach" / "judgments.jsonl"
        assert not log.exists() or log.read_text().strip() == ""

    def test_schema_violation_still_writes_judgment_line(self, repo: Path):
        from atdd.coach.commands.judge_call_sites import (
            invoke_reviewer_concern_judge,
        )

        bad_payload = {"decision": "invalid", "rationale": "", "pr_annotation": ""}
        llm = _register_stub(bad_payload)
        invoke_reviewer_concern_judge(
            review_report=_concern_report(),
            llm=llm,
        )
        log = repo / ".atdd" / "runtime" / "coach" / "judgments.jsonl"
        lines = [json.loads(ln) for ln in log.read_text().splitlines() if ln.strip()]
        assert len(lines) == 1
        assert lines[0]["outcome"] == "schema_violation"
        assert lines[0]["call_site"] == "reviewer_concern"


# ---------------------------------------------------------------------------
# Idempotency — inputs hash stability
# ---------------------------------------------------------------------------


class TestInputsHashStability:
    """Same review report → same inputs_hash (cache-resolvable on --resume)."""

    def test_same_report_same_hash(self):
        from atdd.coach.commands.judge_call_sites import (
            inputs_hash_for_reviewer_concern,
        )

        report = _concern_report()
        h1 = inputs_hash_for_reviewer_concern(review_report=report)
        h2 = inputs_hash_for_reviewer_concern(review_report=report)
        assert h1 == h2

    def test_different_commit_different_hash(self):
        from atdd.coach.commands.judge_call_sites import (
            inputs_hash_for_reviewer_concern,
        )

        r1 = _concern_report(target_commit="aaa1111")
        r2 = _concern_report(target_commit="bbb2222")
        assert inputs_hash_for_reviewer_concern(review_report=r1) != inputs_hash_for_reviewer_concern(review_report=r2)
