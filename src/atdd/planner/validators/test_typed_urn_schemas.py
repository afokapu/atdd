# URN: component:plan:typed-urn-schemas:TypedUrnSchemas:backend:tests
# Runtime: python
# Purpose: The train + interlocking JSON schemas accept the typed URN grammar (#1421) and record the #1410 payload-contract segment decision.
"""Schema-first tests for the typed URN grammar migration (issue #1421).

These lock the contract the migration (worker C4) writes data against:

* ``train.schema.json`` ``train_id`` accepts the typed ``train:<subject>:<slug>``
  form AND — during the migration transition — the legacy ``NNNN-slug`` form, so
  nothing breaks before the data is migrated (schema-first, data-follows).
* ``category`` is a validated *field* on the train (nominal/error/alternate/
  exception), never an identity digit; an optional ordinal ``sort_key`` rides.
* ``train-interlocking.schema.json`` ``route.train_id`` accepts the typed form;
  ``category_digit`` is retired from *required* (kept enum-checked when present)
  so migrated routes may drop it.
* #1410: the interlocking ``payload.contract`` identity is a **2-segment**
  ``domain:resource`` — decided once here; a 3-segment contract is rejected.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest

_SCHEMAS = Path(__file__).resolve().parents[1] / "schemas"
_TRAIN_SCHEMA = _SCHEMAS / "train.schema.json"
_INTERLOCKING_SCHEMA = _SCHEMAS / "train-interlocking.schema.json"


def _schema(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _minimal_train() -> dict:
    return {
        "train_id": "train:artifact-identity:migrate-with-alias",
        "title": "Migrate With Alias",
        "description": "Typed train identity round-trip fixture.",
        "themes": ["commons"],
        "participants": ["wagon:migrate-identities"],
        "sequence": [
            {
                "step": 1,
                "intent": "relocate the legacy train under its subject dir",
                "from": "system:planner",
                "to": "system:planner",
                "artifact": "plan:migrate-identities",
            }
        ],
    }


# ---------------------------------------------------------------------------
# train.schema.json — typed train_id + category field + sort_key
# ---------------------------------------------------------------------------
def test_train_id_accepts_typed_form() -> None:
    jsonschema.validate(_minimal_train(), _schema(_TRAIN_SCHEMA))


def test_train_id_still_accepts_legacy_form_during_migration() -> None:
    doc = _minimal_train()
    doc["train_id"] = "0001-self-compliance-validate"
    jsonschema.validate(doc, _schema(_TRAIN_SCHEMA))


def test_train_id_rejects_garbage() -> None:
    doc = _minimal_train()
    doc["train_id"] = "Train Not A URN"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, _schema(_TRAIN_SCHEMA))


@pytest.mark.parametrize("category", ["nominal", "error", "alternate", "exception"])
def test_train_category_field_accepts_enum(category: str) -> None:
    doc = _minimal_train()
    doc["category"] = category
    jsonschema.validate(doc, _schema(_TRAIN_SCHEMA))


def test_train_category_field_rejects_non_enum() -> None:
    doc = _minimal_train()
    doc["category"] = "3"  # a digit is no longer a category
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, _schema(_TRAIN_SCHEMA))


def test_train_sort_key_is_optional_ordinal() -> None:
    doc = _minimal_train()
    doc["category"] = "nominal"
    doc["sort_key"] = 7
    jsonschema.validate(doc, _schema(_TRAIN_SCHEMA))


def test_train_dependencies_accept_typed_ref() -> None:
    doc = _minimal_train()
    doc["dependencies"] = ["train:artifact-identity:author-registry"]
    jsonschema.validate(doc, _schema(_TRAIN_SCHEMA))


# ---------------------------------------------------------------------------
# train-interlocking.schema.json — typed route.train_id + retired category_digit
# ---------------------------------------------------------------------------
def _minimal_route() -> dict:
    return {
        "route_id": "nominal",
        "category": "nominal",
        "priority": 0,
        "guard_ref": "guard:always",
        "train_id": "train:artifact-identity:migrate-with-alias",
        "train_path": "plan/_trains/artifact-identity/migrate-with-alias.yaml",
        "projection": {"expected_sequence_digest": "deadbeef"},
    }


def _route_schema() -> dict:
    return _schema(_INTERLOCKING_SCHEMA)["definitions"]["route"]


def test_route_train_id_accepts_typed_form() -> None:
    jsonschema.validate(_minimal_route(), _route_schema())


def test_route_train_id_still_accepts_legacy_form() -> None:
    route = _minimal_route()
    route["train_id"] = "3007-match-resolution-standard"
    route["category_digit"] = "0"
    jsonschema.validate(route, _route_schema())


def test_route_category_digit_is_optional() -> None:
    """A migrated route may omit ``category_digit`` (retired from required)."""
    route = _minimal_route()
    assert "category_digit" not in route
    jsonschema.validate(route, _route_schema())


def test_route_category_digit_still_enum_checked_when_present() -> None:
    route = _minimal_route()
    route["category_digit"] = "9"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(route, _route_schema())


# ---------------------------------------------------------------------------
# #1410 — payload.contract is a 2-segment domain:resource identity, decided once
# ---------------------------------------------------------------------------
def _payload_schema() -> dict:
    return _schema(_INTERLOCKING_SCHEMA)["definitions"]["message"]["properties"]["payload"]


def test_payload_contract_two_segments_accepted() -> None:
    jsonschema.validate({"contract": "match:result"}, _payload_schema())


def test_payload_contract_three_segments_rejected_1410() -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"contract": "match:result:extra"}, _payload_schema())
