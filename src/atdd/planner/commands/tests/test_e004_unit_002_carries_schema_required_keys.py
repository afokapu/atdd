# URN: test:author-plan-substrate:author-train:E004-UNIT-002-carries-schema-required-keys
# Acceptance: acc:author-plan-substrate:E004-UNIT-002-carries-schema-required-keys
# WMBT: wmbt:author-plan-substrate:E004
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""E004-UNIT-002 — create_train carries the schema-recognized keys into the per-train doc.

RED: create_train builds train_doc from only five keys and drops `themes` and
`sequence`, both of which train.schema.json marks REQUIRED. Every train the
writer authors is therefore schema-invalid.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import yaml

from atdd.planner.commands.author import create_train

SCHEMA = Path(__file__).resolve().parents[2] / "schemas" / "train.schema.json"


def _full_spec(train_id: str = "0009-demo-train") -> dict:
    return {
        "train_id": train_id,
        "title": "Demo train",
        "description": "a demo train exercising the writer's carry-through",
        "themes": ["commons"],
        "family": "delivery",
        "primary_wagon": "demo-wagon",
        "wagons": ["demo-wagon"],
        "participants": ["wagon:demo-wagon", "system:atdd-cli"],
        "dependencies": ["train:0001-self-compliance-validate"],
        "sequence": [
            {
                "step": 1,
                "intent": "author the plan substrate",
                "from": "wagon:demo-wagon",
                "to": "system:atdd-cli",
                "artifact": "commons:manifest",
            },
        ],
    }


def _author(tmp_path: Path, spec: dict) -> dict:
    plan = tmp_path / "plan"
    (plan / "_trains").mkdir(parents=True)
    (plan / "_trains.yaml").write_text("trains: {}\n", encoding="utf-8")
    per_train = create_train(spec, root=tmp_path)
    return yaml.safe_load(per_train.read_text(encoding="utf-8"))


def test_required_keys_round_trip(tmp_path):
    spec = _full_spec()
    doc = _author(tmp_path, spec)
    assert doc["themes"] == spec["themes"]
    assert doc["sequence"] == spec["sequence"]


def test_optional_keys_round_trip_when_supplied(tmp_path):
    spec = _full_spec()
    doc = _author(tmp_path, spec)
    assert doc["family"] == "delivery"
    assert doc["primary_wagon"] == "demo-wagon"
    assert doc["dependencies"] == ["train:0001-self-compliance-validate"]


def test_optional_keys_absent_when_omitted(tmp_path):
    spec = _full_spec()
    for k in ("family", "primary_wagon", "dependencies"):
        spec.pop(k)
    doc = _author(tmp_path, spec)
    for k in ("family", "primary_wagon", "dependencies"):
        assert k not in doc, f"{k} must not be invented when the caller omitted it"


def test_acceptances_round_trip_when_supplied(tmp_path):
    spec = _full_spec()
    spec["acceptances"] = [
        {"identity": {"urn": "acc:demo-wagon:E001-UNIT-001-demo", "id": "AC-UNIT-001",
                      "purpose": "demo", "phase": "GREEN"}},
    ]
    doc = _author(tmp_path, spec)
    assert doc["acceptances"] == spec["acceptances"]


def test_wagons_is_not_written_into_the_document(tmp_path):
    # train.schema.json sets additionalProperties: false and defines no `wagons`
    # property — `wagons` belongs to the _trains.yaml registry entry only.
    doc = _author(tmp_path, _full_spec())
    assert "wagons" not in doc


def test_authored_train_validates_against_train_schema(tmp_path):
    doc = _author(tmp_path, _full_spec())
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    errors = sorted(jsonschema.Draft7Validator(schema).iter_errors(doc), key=str)
    assert errors == [], "\n".join(
        f"{list(e.absolute_path)}: {e.message}" for e in errors
    )
