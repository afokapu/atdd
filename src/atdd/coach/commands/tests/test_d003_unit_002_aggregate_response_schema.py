# URN: test:judge-ambiguous-decisions:judge-and-issue-review:D003-UNIT-002-aggregate-response-schema
# Acceptance: acc:judge-ambiguous-decisions:D003-UNIT-002-aggregate-response-schema
# WMBT: wmbt:judge-ambiguous-decisions:D003
# Phase: RED
# Layer: unit
"""D003-UNIT-002 — judge call site #5 frozen response schema.

Per spec §6.9 #5 / §6.10 (and issue #523):

  ``judge-issue-review-aggregate.response.schema.json`` freezes the
  consolidation contract:

  ``{
      decision: accept | request_revision | escalate,
      consolidated_feedback: non-empty string,
      dominant_dimensions: non-empty subset of the five §6.10 dimensions
                           (systemic, ambiguities, gap, regression,
                           comprehensiveness)
  }``

Invalid values fail validation loudly. At least one valid example
fixture is committed at
``src/atdd/coach/schemas/fixtures/judge-issue-review-aggregate/``.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest


pytestmark = [pytest.mark.platform]


_SCHEMAS_DIR = (
    Path(__file__).resolve().parents[2] / "schemas"
)
_SCHEMA_PATH = _SCHEMAS_DIR / "judge-issue-review-aggregate.response.schema.json"
_FIXTURES_DIR = _SCHEMAS_DIR / "fixtures" / "judge-issue-review-aggregate"


def _load_schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text())


class TestSchemaIsCommitted:
    def test_schema_file_exists(self):
        assert _SCHEMA_PATH.exists(), (
            f"frozen response contract missing at {_SCHEMA_PATH}"
        )

    def test_schema_parses_as_json_schema(self):
        schema = _load_schema()
        # Construct the validator — this raises if the schema itself is malformed.
        jsonschema.Draft202012Validator.check_schema(schema)

    def test_schema_id_matches_filename(self):
        schema = _load_schema()
        assert schema.get("$id") == "judge-issue-review-aggregate.response.schema.json"


class TestRequiredFields:
    def test_decision_is_required(self):
        schema = _load_schema()
        validator = jsonschema.Draft202012Validator(schema)
        with pytest.raises(jsonschema.ValidationError):
            validator.validate({
                "consolidated_feedback": "x",
                "dominant_dimensions": ["gap"],
            })

    def test_consolidated_feedback_is_required(self):
        schema = _load_schema()
        validator = jsonschema.Draft202012Validator(schema)
        with pytest.raises(jsonschema.ValidationError):
            validator.validate({
                "decision": "accept",
                "dominant_dimensions": ["gap"],
            })

    def test_dominant_dimensions_is_required(self):
        schema = _load_schema()
        validator = jsonschema.Draft202012Validator(schema)
        with pytest.raises(jsonschema.ValidationError):
            validator.validate({
                "decision": "accept",
                "consolidated_feedback": "x",
            })


class TestDecisionEnum:
    @pytest.mark.parametrize("value", ["accept", "request_revision", "escalate"])
    def test_each_valid_decision_passes(self, value: str):
        schema = _load_schema()
        jsonschema.Draft202012Validator(schema).validate({
            "decision": value,
            "consolidated_feedback": "ok",
            "dominant_dimensions": ["gap"],
        })

    @pytest.mark.parametrize("value", ["proceed", "block", "REQUEST_REVISION", "", "request-revision"])
    def test_invalid_decision_fails(self, value: str):
        schema = _load_schema()
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate({
                "decision": value,
                "consolidated_feedback": "ok",
                "dominant_dimensions": ["gap"],
            })


class TestConsolidatedFeedbackNonEmpty:
    def test_empty_string_fails(self):
        schema = _load_schema()
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate({
                "decision": "accept",
                "consolidated_feedback": "",
                "dominant_dimensions": ["gap"],
            })

    def test_non_string_fails(self):
        schema = _load_schema()
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate({
                "decision": "accept",
                "consolidated_feedback": 42,
                "dominant_dimensions": ["gap"],
            })


class TestDominantDimensions:
    @pytest.mark.parametrize(
        "value",
        ["systemic", "ambiguities", "gap", "regression", "comprehensiveness"],
    )
    def test_each_dimension_passes(self, value: str):
        schema = _load_schema()
        jsonschema.Draft202012Validator(schema).validate({
            "decision": "request_revision",
            "consolidated_feedback": "x",
            "dominant_dimensions": [value],
        })

    def test_unknown_dimension_fails(self):
        schema = _load_schema()
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate({
                "decision": "accept",
                "consolidated_feedback": "x",
                "dominant_dimensions": ["unknown"],
            })

    def test_empty_array_fails(self):
        schema = _load_schema()
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate({
                "decision": "accept",
                "consolidated_feedback": "x",
                "dominant_dimensions": [],
            })

    def test_non_array_fails(self):
        schema = _load_schema()
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate({
                "decision": "accept",
                "consolidated_feedback": "x",
                "dominant_dimensions": "gap",
            })

    def test_subset_of_two_dimensions_passes(self):
        schema = _load_schema()
        jsonschema.Draft202012Validator(schema).validate({
            "decision": "request_revision",
            "consolidated_feedback": "x",
            "dominant_dimensions": ["gap", "regression"],
        })


class TestFixtureCommitted:
    def test_fixtures_dir_exists(self):
        assert _FIXTURES_DIR.is_dir(), (
            f"committed fixtures dir missing at {_FIXTURES_DIR}"
        )

    def test_at_least_one_valid_fixture_committed(self):
        fixtures = sorted(_FIXTURES_DIR.glob("*.json"))
        assert fixtures, (
            f"no fixtures committed in {_FIXTURES_DIR}; expected at least one"
        )
        schema = _load_schema()
        validator = jsonschema.Draft202012Validator(schema)
        for fx in fixtures:
            payload = json.loads(fx.read_text())
            validator.validate(payload)
