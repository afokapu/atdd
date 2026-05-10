# URN: test:judge-ambiguous-decisions:judge-and-issue-review:D004-UNIT-002-consolidation-response-schema
# Acceptance: acc:judge-ambiguous-decisions:D004-UNIT-002-consolidation-response-schema
# WMBT: wmbt:judge-ambiguous-decisions:D004
# Phase: GREEN
# Layer: unit
"""D004-UNIT-002 -- consolidation response schema frozen and validates.

Per spec §6.9 #6 (and issue #524):

  * ``judge-superseded-rule-consolidation.response.schema.json`` freezes the
    response contract: ``{guidance, suggested_aliases, canonical_rule_id,
    fix_hint}``.
  * ``guidance`` is a non-empty migration narrative referencing both the
    legacy alias and the canonical rule_id.
  * ``suggested_aliases`` lists zero or more deprecated IDs.
  * ``canonical_rule_id`` is a registry-resolvable string.
  * ``fix_hint`` is a non-empty string.
  * At least one valid example fixture is committed.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

pytestmark = [pytest.mark.platform]


_SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "schemas"

_SCHEMA = _SCHEMAS_DIR / "judge-superseded-rule-consolidation.response.schema.json"
_FIXTURES = _SCHEMAS_DIR / "fixtures" / "judge-superseded-rule-consolidation"


class TestSupersededRuleConsolidationSchema:
    def test_schema_file_exists(self):
        assert _SCHEMA.exists(), (
            f"frozen response contract missing at {_SCHEMA}"
        )

    def test_schema_parses(self):
        schema = json.loads(_SCHEMA.read_text())
        jsonschema.Draft202012Validator.check_schema(schema)

    def test_schema_id_matches_filename(self):
        schema = json.loads(_SCHEMA.read_text())
        assert schema.get("$id") == "judge-superseded-rule-consolidation.response.schema.json"

    def test_valid_full_response_passes(self):
        schema = json.loads(_SCHEMA.read_text())
        jsonschema.Draft202012Validator(schema).validate({
            "guidance": "Rule OLD-ID has been superseded by coder.new.rule.",
            "suggested_aliases": ["OLD-ID", "old-id-legacy"],
            "canonical_rule_id": "coder.new.rule",
            "fix_hint": "Replace OLD-ID references with coder.new.rule in suppress markers.",
        })

    def test_valid_empty_suggested_aliases_passes(self):
        schema = json.loads(_SCHEMA.read_text())
        jsonschema.Draft202012Validator(schema).validate({
            "guidance": "Migrate from legacy to canonical.",
            "suggested_aliases": [],
            "canonical_rule_id": "coder.new.rule",
            "fix_hint": "Update references.",
        })

    def test_missing_guidance_fails(self):
        schema = json.loads(_SCHEMA.read_text())
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate({
                "suggested_aliases": [],
                "canonical_rule_id": "coder.new.rule",
                "fix_hint": "fix it",
            })

    def test_empty_guidance_fails(self):
        schema = json.loads(_SCHEMA.read_text())
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate({
                "guidance": "",
                "suggested_aliases": [],
                "canonical_rule_id": "coder.new.rule",
                "fix_hint": "fix it",
            })

    def test_missing_canonical_rule_id_fails(self):
        schema = json.loads(_SCHEMA.read_text())
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate({
                "guidance": "migrate now",
                "suggested_aliases": [],
                "fix_hint": "fix it",
            })

    def test_empty_canonical_rule_id_fails(self):
        schema = json.loads(_SCHEMA.read_text())
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate({
                "guidance": "migrate now",
                "suggested_aliases": [],
                "canonical_rule_id": "",
                "fix_hint": "fix it",
            })

    def test_missing_fix_hint_fails(self):
        schema = json.loads(_SCHEMA.read_text())
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate({
                "guidance": "migrate now",
                "suggested_aliases": [],
                "canonical_rule_id": "coder.new.rule",
            })

    def test_empty_fix_hint_fails(self):
        schema = json.loads(_SCHEMA.read_text())
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate({
                "guidance": "migrate now",
                "suggested_aliases": [],
                "canonical_rule_id": "coder.new.rule",
                "fix_hint": "",
            })

    def test_suggested_aliases_must_be_strings(self):
        schema = json.loads(_SCHEMA.read_text())
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate({
                "guidance": "migrate now",
                "suggested_aliases": [123],
                "canonical_rule_id": "coder.new.rule",
                "fix_hint": "fix it",
            })

    def test_additional_properties_rejected(self):
        schema = json.loads(_SCHEMA.read_text())
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate({
                "guidance": "migrate now",
                "suggested_aliases": [],
                "canonical_rule_id": "coder.new.rule",
                "fix_hint": "fix it",
                "extra_field": "not allowed",
            })

    def test_fixtures_dir_exists(self):
        assert _FIXTURES.is_dir(), f"fixtures dir missing at {_FIXTURES}"

    def test_at_least_one_valid_fixture(self):
        fixtures = sorted(_FIXTURES.glob("*.json"))
        assert fixtures, f"no fixtures in {_FIXTURES}"
        schema = json.loads(_SCHEMA.read_text())
        for fx in fixtures:
            jsonschema.Draft202012Validator(schema).validate(json.loads(fx.read_text()))
