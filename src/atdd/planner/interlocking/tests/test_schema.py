"""Schema shape tests for train-interlocking.schema.json (#1248)."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest

from atdd.planner.interlocking.tests._fixtures import interlocking_doc

SCHEMA_PATH = (
    Path(__file__).resolve().parents[2] / "schemas" / "train-interlocking.schema.json"
)


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def test_schema_file_exists_and_is_draft7():
    schema = _schema()
    jsonschema.Draft7Validator.check_schema(schema)


def test_valid_document_passes():
    jsonschema.validate(interlocking_doc(), _schema())


def test_unknown_top_level_field_rejected():
    doc = interlocking_doc()
    doc["cargo"] = {"artifact_urn": "x", "artifact_data": {"secret": 1}}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, _schema())


def test_exposed_true_requires_an_action():
    doc = interlocking_doc()
    doc["entrypoint"] = {"exposed": True, "actions": [], "reason": None}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, _schema())


def test_exposed_false_requires_reason():
    doc = interlocking_doc()
    doc["entrypoint"] = {"exposed": False, "actions": [], "reason": None}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, _schema())


def test_exposed_false_with_reason_passes():
    doc = interlocking_doc()
    doc["entrypoint"] = {
        "exposed": False,
        "actions": [],
        "reason": "internal-transition-only",
    }
    jsonschema.validate(doc, _schema())


def test_message_requires_contract_or_no_payload_reason():
    doc = interlocking_doc()
    doc["messages"][0]["payload"] = {"contract": None, "no_payload_reason": None}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, _schema())


def test_route_resolution_strategy_is_enumerated():
    doc = interlocking_doc()
    doc["route_resolution"]["strategy"] = "round_robin"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, _schema())


def test_route_category_digit_is_rejected():
    # Retired by #1421/#1440: category is a FIELD on the target train, so a route
    # carrying the identity digit is no longer a valid document at all.
    doc = interlocking_doc()
    doc["routes"][0]["category_digit"] = "0"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, _schema())
