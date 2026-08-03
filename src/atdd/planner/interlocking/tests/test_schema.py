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


# ---------------------------------------------------------------------------
# Typed obligation references (#1546).
#
# These are fault-injection tests: each one feeds the schema a document in the
# shape that was previously ACCEPTED and asserts it is now rejected. A test that
# only round-trips the repaired fixture would pass forever even if the grammar
# silently regressed to the one-segment form, so each retired shape gets an
# explicit refutation.
# ---------------------------------------------------------------------------
def test_one_segment_wmbt_ref_on_invariant_is_rejected():
    """The retired `^wmbt:[a-z][a-z0-9-]*$` grammar can never name a real WMBT."""
    doc = interlocking_doc()
    doc["invariants"][0]["wmbt_ref"] = "wmbt:pressure-collapse"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, _schema())


def test_canonical_two_segment_wmbt_ref_on_invariant_passes():
    doc = interlocking_doc()
    doc["invariants"][0]["wmbt_ref"] = "wmbt:pressure-collapse:D001"
    jsonschema.validate(doc, _schema())


@pytest.mark.parametrize("bad", [
    "wmbt:pressure-collapse",            # one segment
    "wmbt:pressure-collapse:X001",       # category letter outside DLPCEMYRK
    "wmbt:pressure-collapse:C1",         # not three digits
    "wmbt:Pressure-Collapse:C001",       # wagon not kebab-case
    "acc:pressure-collapse:C001",        # wrong namespace
])
def test_malformed_wmbt_refs_are_rejected_on_every_surface(bad):
    """Every surface that can name an obligation enforces the same grammar."""
    for surface, mutate in (
        ("message",  lambda d: d["messages"][0].__setitem__("wmbt_refs", [bad])),
        ("guard",    lambda d: d["fragments"][0]["guards"][0].__setitem__("wmbt_refs", [bad])),
        ("fragment", lambda d: d["fragments"][0].__setitem__("wmbt_refs", [bad])),
        ("residual", lambda d: d["residuals"][0].__setitem__("wmbt_refs", [bad])),
    ):
        doc = interlocking_doc()
        mutate(doc)
        with pytest.raises(jsonschema.ValidationError, match="wmbt"):
            jsonschema.validate(doc, _schema())


def test_free_acceptance_slug_on_residual_is_rejected():
    """`acceptance:<slug>` resolved to nothing; only `acc:` URNs are accepted."""
    doc = interlocking_doc()
    doc["residuals"][0]["acceptance_ref"] = "acceptance:blitz-owns-no-grid"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, _schema())


def test_duplicate_wmbt_refs_on_a_surface_are_rejected():
    doc = interlocking_doc()
    doc["messages"][0]["wmbt_refs"] = [
        "wmbt:pressure-collapse:C001",
        "wmbt:pressure-collapse:C001",
    ]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, _schema())
