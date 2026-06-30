"""Registry shape + optional train source_interlocking back-ref tests (#1248)."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest
import yaml

from atdd.planner.interlocking.tests._fixtures import write_tree

_SCHEMAS = Path(__file__).resolve().parents[2] / "schemas"


def _schema(name: str) -> dict:
    return json.loads((_SCHEMAS / name).read_text(encoding="utf-8"))


def test_registry_schema_validates_generated_registry(tmp_path):
    write_tree(tmp_path)
    registry = yaml.safe_load(
        (tmp_path / "plan" / "_trains" / "_interlockings.yaml").read_text(encoding="utf-8")
    )
    jsonschema.validate(registry, _schema("train-interlocking-registry.schema.json"))


def test_registry_schema_rejects_bad_interlocking_id():
    registry = {
        "version": "1.0",
        "interlockings": [{"interlocking_id": "not-prefixed", "path": "x.yaml"}],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(registry, _schema("train-interlocking-registry.schema.json"))


def _minimal_train() -> dict:
    return {
        "train_id": "3007-match-resolution-standard",
        "title": "Train",
        "description": "Linear train for back-ref test.",
        "themes": ["match"],
        "participants": ["wagon:blitz", "wagon:player"],
        "sequence": [
            {
                "step": 1,
                "intent": "Close match on quorum",
                "from": "wagon:blitz",
                "to": "wagon:player",
                "artifact": "match:result",
            }
        ],
    }


def test_train_schema_accepts_optional_source_interlocking():
    train = _minimal_train()
    train["source_interlocking"] = {
        "interlocking_id": "interlocking:match-resolution",
        "route_id": "nominal-all-voted",
        "projection_digest": "abc123",
    }
    jsonschema.validate(train, _schema("train.schema.json"))


def test_train_schema_still_valid_without_back_ref():
    jsonschema.validate(_minimal_train(), _schema("train.schema.json"))


def test_source_interlocking_requires_route_id():
    train = _minimal_train()
    train["source_interlocking"] = {"interlocking_id": "interlocking:match-resolution"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(train, _schema("train.schema.json"))
