# URN: test:judge-ambiguous-decisions:judge-and-issue-review:D002-UNIT-002-response-schemas-frozen-and-validate
# Acceptance: acc:judge-ambiguous-decisions:D002-UNIT-002-response-schemas-frozen-and-validate
# WMBT: wmbt:judge-ambiguous-decisions:D002
# Phase: RED
# Layer: unit
"""D002-UNIT-002 -- frozen response schemas for call sites #1, #3, #4.

Per spec S6.9 (and issue #522):

  * ``judge-borderline-tier1.response.schema.json``:
    ``{decision: pass|respawn|annotate, confidence: 0..1, rationale}``
  * ``judge-retry-vs-escalate.response.schema.json``:
    ``{decision: retry|escalate, reasoning}``
  * ``judge-cross-phase-regression.response.schema.json``:
    ``{decision: fix_in_place|reopen_prior_phase|escalate, target_phase, rationale}``

Invalid values fail validation loudly. At least one valid example fixture
is committed per schema at ``src/atdd/coach/schemas/fixtures/``.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest


pytestmark = [pytest.mark.platform]


_SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "schemas"


# ---------------------------------------------------------------------------
# Call site #1 -- borderline tier-1
# ---------------------------------------------------------------------------


_BORDERLINE_SCHEMA = _SCHEMAS_DIR / "judge-borderline-tier1.response.schema.json"
_BORDERLINE_FIXTURES = _SCHEMAS_DIR / "fixtures" / "judge-borderline-tier1"


class TestBorderlineTier1Schema:
    def test_schema_file_exists(self):
        assert _BORDERLINE_SCHEMA.exists(), (
            f"frozen response contract missing at {_BORDERLINE_SCHEMA}"
        )

    def test_schema_parses(self):
        schema = json.loads(_BORDERLINE_SCHEMA.read_text())
        jsonschema.Draft202012Validator.check_schema(schema)

    def test_schema_id_matches_filename(self):
        schema = json.loads(_BORDERLINE_SCHEMA.read_text())
        assert schema.get("$id") == "judge-borderline-tier1.response.schema.json"

    @pytest.mark.parametrize("decision", ["pass", "respawn", "annotate"])
    def test_valid_decision_passes(self, decision: str):
        schema = json.loads(_BORDERLINE_SCHEMA.read_text())
        jsonschema.Draft202012Validator(schema).validate({
            "decision": decision,
            "confidence": 0.7,
            "rationale": "borderline case",
        })

    @pytest.mark.parametrize("decision", ["block", "retry", "PASS", "", "proceed"])
    def test_invalid_decision_fails(self, decision: str):
        schema = json.loads(_BORDERLINE_SCHEMA.read_text())
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate({
                "decision": decision,
                "confidence": 0.7,
                "rationale": "test",
            })

    def test_confidence_below_zero_fails(self):
        schema = json.loads(_BORDERLINE_SCHEMA.read_text())
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate({
                "decision": "pass",
                "confidence": -0.1,
                "rationale": "test",
            })

    def test_confidence_above_one_fails(self):
        schema = json.loads(_BORDERLINE_SCHEMA.read_text())
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate({
                "decision": "pass",
                "confidence": 1.5,
                "rationale": "test",
            })

    def test_missing_confidence_fails(self):
        schema = json.loads(_BORDERLINE_SCHEMA.read_text())
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate({
                "decision": "pass",
                "rationale": "test",
            })

    def test_missing_rationale_fails(self):
        schema = json.loads(_BORDERLINE_SCHEMA.read_text())
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate({
                "decision": "pass",
                "confidence": 0.7,
            })

    def test_empty_rationale_fails(self):
        schema = json.loads(_BORDERLINE_SCHEMA.read_text())
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate({
                "decision": "pass",
                "confidence": 0.7,
                "rationale": "",
            })

    def test_fixtures_dir_exists(self):
        assert _BORDERLINE_FIXTURES.is_dir(), (
            f"fixtures dir missing at {_BORDERLINE_FIXTURES}"
        )

    def test_at_least_one_valid_fixture(self):
        fixtures = sorted(_BORDERLINE_FIXTURES.glob("*.json"))
        assert fixtures, f"no fixtures in {_BORDERLINE_FIXTURES}"
        schema = json.loads(_BORDERLINE_SCHEMA.read_text())
        for fx in fixtures:
            jsonschema.Draft202012Validator(schema).validate(json.loads(fx.read_text()))


# ---------------------------------------------------------------------------
# Call site #3 -- retry-vs-escalate
# ---------------------------------------------------------------------------


_RETRY_SCHEMA = _SCHEMAS_DIR / "judge-retry-vs-escalate.response.schema.json"
_RETRY_FIXTURES = _SCHEMAS_DIR / "fixtures" / "judge-retry-vs-escalate"


class TestRetryVsEscalateSchema:
    def test_schema_file_exists(self):
        assert _RETRY_SCHEMA.exists()

    def test_schema_parses(self):
        schema = json.loads(_RETRY_SCHEMA.read_text())
        jsonschema.Draft202012Validator.check_schema(schema)

    def test_schema_id_matches_filename(self):
        schema = json.loads(_RETRY_SCHEMA.read_text())
        assert schema.get("$id") == "judge-retry-vs-escalate.response.schema.json"

    @pytest.mark.parametrize("decision", ["retry", "escalate"])
    def test_valid_decision_passes(self, decision: str):
        schema = json.loads(_RETRY_SCHEMA.read_text())
        jsonschema.Draft202012Validator(schema).validate({
            "decision": decision,
            "reasoning": "one more attempt likely to succeed",
        })

    @pytest.mark.parametrize("decision", ["pass", "block", "RETRY", "", "proceed"])
    def test_invalid_decision_fails(self, decision: str):
        schema = json.loads(_RETRY_SCHEMA.read_text())
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate({
                "decision": decision,
                "reasoning": "test",
            })

    def test_missing_reasoning_fails(self):
        schema = json.loads(_RETRY_SCHEMA.read_text())
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate({
                "decision": "retry",
            })

    def test_empty_reasoning_fails(self):
        schema = json.loads(_RETRY_SCHEMA.read_text())
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate({
                "decision": "retry",
                "reasoning": "",
            })

    def test_fixtures_dir_exists(self):
        assert _RETRY_FIXTURES.is_dir()

    def test_at_least_one_valid_fixture(self):
        fixtures = sorted(_RETRY_FIXTURES.glob("*.json"))
        assert fixtures, f"no fixtures in {_RETRY_FIXTURES}"
        schema = json.loads(_RETRY_SCHEMA.read_text())
        for fx in fixtures:
            jsonschema.Draft202012Validator(schema).validate(json.loads(fx.read_text()))


# ---------------------------------------------------------------------------
# Call site #4 -- cross-phase regression
# ---------------------------------------------------------------------------


_REGRESSION_SCHEMA = _SCHEMAS_DIR / "judge-cross-phase-regression.response.schema.json"
_REGRESSION_FIXTURES = _SCHEMAS_DIR / "fixtures" / "judge-cross-phase-regression"


class TestCrossPhaseRegressionSchema:
    def test_schema_file_exists(self):
        assert _REGRESSION_SCHEMA.exists()

    def test_schema_parses(self):
        schema = json.loads(_REGRESSION_SCHEMA.read_text())
        jsonschema.Draft202012Validator.check_schema(schema)

    def test_schema_id_matches_filename(self):
        schema = json.loads(_REGRESSION_SCHEMA.read_text())
        assert schema.get("$id") == "judge-cross-phase-regression.response.schema.json"

    @pytest.mark.parametrize("decision", ["fix_in_place", "reopen_prior_phase", "escalate"])
    def test_valid_decision_passes(self, decision: str):
        schema = json.loads(_REGRESSION_SCHEMA.read_text())
        jsonschema.Draft202012Validator(schema).validate({
            "decision": decision,
            "target_phase": "GREEN",
            "rationale": "regression detected",
        })

    @pytest.mark.parametrize("decision", ["pass", "block", "FIX_IN_PLACE", "", "proceed"])
    def test_invalid_decision_fails(self, decision: str):
        schema = json.loads(_REGRESSION_SCHEMA.read_text())
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate({
                "decision": decision,
                "target_phase": "GREEN",
                "rationale": "test",
            })

    def test_missing_target_phase_fails(self):
        schema = json.loads(_REGRESSION_SCHEMA.read_text())
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate({
                "decision": "fix_in_place",
                "rationale": "test",
            })

    def test_missing_rationale_fails(self):
        schema = json.loads(_REGRESSION_SCHEMA.read_text())
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate({
                "decision": "fix_in_place",
                "target_phase": "GREEN",
            })

    def test_empty_rationale_fails(self):
        schema = json.loads(_REGRESSION_SCHEMA.read_text())
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate({
                "decision": "fix_in_place",
                "target_phase": "GREEN",
                "rationale": "",
            })

    def test_fixtures_dir_exists(self):
        assert _REGRESSION_FIXTURES.is_dir()

    def test_at_least_one_valid_fixture(self):
        fixtures = sorted(_REGRESSION_FIXTURES.glob("*.json"))
        assert fixtures, f"no fixtures in {_REGRESSION_FIXTURES}"
        schema = json.loads(_REGRESSION_SCHEMA.read_text())
        for fx in fixtures:
            jsonschema.Draft202012Validator(schema).validate(json.loads(fx.read_text()))
