# URN: test:judge-ambiguous-decisions:judge-and-issue-review:D005-UNIT-002-five-dimensions-per-pass
# Acceptance: acc:judge-ambiguous-decisions:D005-UNIT-002-five-dimensions-per-pass
# WMBT: wmbt:judge-ambiguous-decisions:D005
# Phase: RED
# Layer: application
"""D005-UNIT-002 — each per-pass response carries the five fixed
dimensions (systemic, ambiguities, gap, regression, comprehensiveness)
and conforms to ``issue-review-pass.response.schema.json``. Findings
that map to a known rule-id via ``bind_rule()`` populate the
``rule_id`` field; unknown ids resolve to ``null``. Per-pass content
folds into ``aggregate.json`` (``issue-review-aggregate.schema.json``).
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
import yaml


pytestmark = [pytest.mark.platform]


REPO_ROOT = Path(__file__).resolve().parents[5]
SCHEMAS_DIR = REPO_ROOT / "src" / "atdd" / "coach" / "schemas"


def _pass_schema() -> dict:
    return json.loads(
        (SCHEMAS_DIR / "issue-review-pass.response.schema.json").read_text()
    )


def _aggregate_schema() -> dict:
    return json.loads(
        (SCHEMAS_DIR / "issue-review-aggregate.schema.json").read_text()
    )


# ---------------------------------------------------------------------------
# Stub helpers
# ---------------------------------------------------------------------------


class _StubClient:
    def __init__(self, payload):
        self._payload = payload

    def invoke(self, prompt: str):
        return self._payload


def _all_pass_dimensions() -> dict:
    return {
        "dimensions": {
            "systemic":          {"verdict": "pass", "findings": []},
            "ambiguities":       {"verdict": "pass", "findings": []},
            "gap":               {"verdict": "pass", "findings": []},
            "regression":        {"verdict": "pass", "findings": []},
            "comprehensiveness": {"verdict": "pass", "findings": []},
        }
    }


def _payload_with_finding(*, dimension: str, rule_id, severity: int = 3, detail: str = "x") -> dict:
    payload = _all_pass_dimensions()
    payload["dimensions"][dimension] = {
        "verdict": "concern",
        "findings": [
            {"rule_id": rule_id, "severity": severity, "detail": detail},
        ],
    }
    return payload


def _register(name: str, payload):
    from atdd.coach.commands import judge as judge_mod

    judge_mod.register_llm_client(name, lambda: _StubClient(payload))


@pytest.fixture(autouse=True)
def _reset_registry():
    from atdd.coach.commands import judge as judge_mod

    snapshot = dict(judge_mod.LLM_REGISTRY)
    judge_mod.LLM_REGISTRY.clear()
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
# AC-UNIT-002: per-pass response carries the five dimensions
# ---------------------------------------------------------------------------


class TestPerPassFiveDimensions:
    def test_each_pass_file_validates_against_pass_schema(
        self, review_workspace: Path
    ):
        from atdd.coach.commands.issue_review import run

        for name in ("haiku", "mini", "flash"):
            _register(name, _all_pass_dimensions())
        rc = run(
            issue_number=99,
            passes=3,
            llms=["haiku", "mini", "flash"],
        )
        assert rc == 0

        schema = _pass_schema()
        review_dir = review_workspace / ".atdd" / "runtime" / "issue-reviews" / "99"
        for path in sorted(review_dir.glob("pass-*.json")):
            record = json.loads(path.read_text())
            jsonschema.Draft202012Validator(schema).validate(record)

    def test_pass_record_dimension_keys_are_the_five_fixed(
        self, review_workspace: Path
    ):
        from atdd.coach.commands.issue_review import run

        _register("haiku", _all_pass_dimensions())
        _register("mini",  _all_pass_dimensions())
        run(
            issue_number=7,
            passes=2,
            llms=["haiku", "mini"],
        )
        record = json.loads(
            (review_workspace / ".atdd" / "runtime" / "issue-reviews" / "7" / "pass-1-haiku.json").read_text()
        )
        assert set(record["dimensions"].keys()) == {
            "systemic", "ambiguities", "gap", "regression", "comprehensiveness",
        }

    def test_finding_with_known_rule_id_keeps_it(
        self, review_workspace: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from atdd.coach.commands import issue_review as ir
        from atdd.coach.commands.issue_review import run

        # Patch bind_rule so the test does not depend on the live registry's
        # rule inventory. A "known" id resolves; an "unknown" id raises.
        class _FakeRuleNotFound(Exception):
            pass

        def _fake_bind_rule(rule_id: str):
            if rule_id == "coder.logging.coach-silent-swallow":
                class _Meta:
                    pass
                meta = _Meta()
                meta.rule_id = rule_id
                return meta
            raise _FakeRuleNotFound(rule_id)

        monkeypatch.setattr(ir, "bind_rule", _fake_bind_rule)
        monkeypatch.setattr(ir, "RuleBindingError", _FakeRuleNotFound)

        _register("haiku", _payload_with_finding(
            dimension="ambiguities",
            rule_id="coder.logging.coach-silent-swallow",
            severity=3,
            detail="silent swallow without UNTIL",
        ))
        _register("mini", _all_pass_dimensions())
        rc = run(
            issue_number=11,
            passes=2,
            llms=["haiku", "mini"],
        )
        assert rc == 0

        record = json.loads(
            (review_workspace / ".atdd" / "runtime" / "issue-reviews" / "11" / "pass-1-haiku.json").read_text()
        )
        finding = record["dimensions"]["ambiguities"]["findings"][0]
        assert finding["rule_id"] == "coder.logging.coach-silent-swallow"

    def test_finding_with_unknown_rule_id_resolves_to_null(
        self, review_workspace: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from atdd.coach.commands import issue_review as ir
        from atdd.coach.commands.issue_review import run

        class _FakeRuleNotFound(Exception):
            pass

        def _fake_bind_rule(rule_id: str):
            raise _FakeRuleNotFound(rule_id)

        monkeypatch.setattr(ir, "bind_rule", _fake_bind_rule)
        monkeypatch.setattr(ir, "RuleBindingError", _FakeRuleNotFound)

        _register("haiku", _payload_with_finding(
            dimension="gap",
            rule_id="not.a.real.rule",
            severity=2,
            detail="LLM hallucinated a rule id",
        ))
        _register("mini", _all_pass_dimensions())
        rc = run(
            issue_number=12,
            passes=2,
            llms=["haiku", "mini"],
        )
        assert rc == 0

        record = json.loads(
            (review_workspace / ".atdd" / "runtime" / "issue-reviews" / "12" / "pass-1-haiku.json").read_text()
        )
        finding = record["dimensions"]["gap"]["findings"][0]
        assert finding["rule_id"] is None


# ---------------------------------------------------------------------------
# AC-UNIT-002: aggregate.json folds the five dimensions
# ---------------------------------------------------------------------------


class TestAggregateRollupFiveDimensions:
    def test_aggregate_validates_against_aggregate_schema(
        self, review_workspace: Path
    ):
        from atdd.coach.commands.issue_review import run

        for name in ("haiku", "mini"):
            _register(name, _all_pass_dimensions())
        run(
            issue_number=21,
            passes=2,
            llms=["haiku", "mini"],
        )

        agg_path = review_workspace / ".atdd" / "runtime" / "issue-reviews" / "21" / "aggregate.json"
        agg = json.loads(agg_path.read_text())
        jsonschema.Draft202012Validator(_aggregate_schema()).validate(agg)

    def test_aggregate_per_dimension_concern_when_any_pass_concerned(
        self, review_workspace: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from atdd.coach.commands import issue_review as ir
        from atdd.coach.commands.issue_review import run

        # Disable rule-binding lookups for this test (irrelevant to the
        # aggregate-roll-up shape).
        class _Skip(Exception):
            pass
        monkeypatch.setattr(ir, "bind_rule", lambda r: (_ for _ in ()).throw(_Skip(r)))
        monkeypatch.setattr(ir, "RuleBindingError", _Skip)

        # Pass 1 concerned in `gap`; pass 2 all-pass. Aggregate gap → concern.
        _register("haiku", _payload_with_finding(
            dimension="gap", rule_id=None, detail="missing edge case"
        ))
        _register("mini", _all_pass_dimensions())
        run(
            issue_number=22,
            passes=2,
            llms=["haiku", "mini"],
        )

        agg = json.loads(
            (review_workspace / ".atdd" / "runtime" / "issue-reviews" / "22" / "aggregate.json").read_text()
        )
        assert agg["dimensions"]["gap"]["verdict"] == "concern"
        assert agg["dimensions"]["gap"]["concern_passes"] == [1]
        # Other dimensions remain pass.
        assert agg["dimensions"]["ambiguities"]["verdict"] == "pass"
        assert agg["dimensions"]["regression"]["verdict"] == "pass"

    def test_aggregate_findings_carry_pass_provenance(
        self, review_workspace: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from atdd.coach.commands import issue_review as ir
        from atdd.coach.commands.issue_review import run

        class _Skip(Exception):
            pass
        monkeypatch.setattr(ir, "bind_rule", lambda r: (_ for _ in ()).throw(_Skip(r)))
        monkeypatch.setattr(ir, "RuleBindingError", _Skip)

        _register("haiku", _payload_with_finding(
            dimension="ambiguities", rule_id=None, detail="ambiguous wording"
        ))
        _register("mini", _all_pass_dimensions())
        run(
            issue_number=23,
            passes=2,
            llms=["haiku", "mini"],
        )

        agg = json.loads(
            (review_workspace / ".atdd" / "runtime" / "issue-reviews" / "23" / "aggregate.json").read_text()
        )
        # Exactly one finding (only pass 1 surfaced one) with full provenance.
        findings = agg["findings"]
        assert len(findings) == 1
        f = findings[0]
        assert f["pass_id"] == 1
        assert f["llm"] == "haiku"
        assert f["dimension"] == "ambiguities"
        assert f["detail"] == "ambiguous wording"

    def test_aggregate_dedupes_findings_when_rule_id_and_detail_match(
        self, review_workspace: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from atdd.coach.commands import issue_review as ir
        from atdd.coach.commands.issue_review import run

        class _FakeRuleNotFound(Exception):
            pass

        def _fake_bind(rule_id: str):
            class _Meta:
                pass
            m = _Meta(); m.rule_id = rule_id
            return m

        monkeypatch.setattr(ir, "bind_rule", _fake_bind)
        monkeypatch.setattr(ir, "RuleBindingError", _FakeRuleNotFound)

        # Both passes surface the same (rule_id, detail) pair → dedup to one.
        common = _payload_with_finding(
            dimension="regression",
            rule_id="some.rule.id",
            detail="same finding from two LLMs",
        )
        _register("haiku", common)
        _register("mini",  common)
        run(
            issue_number=24,
            passes=2,
            llms=["haiku", "mini"],
        )

        agg = json.loads(
            (review_workspace / ".atdd" / "runtime" / "issue-reviews" / "24" / "aggregate.json").read_text()
        )
        # Dedup by (rule_id, detail) when both are populated → exactly one.
        regression_findings = [
            f for f in agg["findings"] if f["dimension"] == "regression"
        ]
        assert len(regression_findings) == 1
        # Per-dimension verdict still records both passes were concerned.
        assert agg["dimensions"]["regression"]["concern_passes"] == [1, 2]
