# URN: test:author-plan-substrate:author-feature:E002-UNIT-001-canonical-home-and-schema
# Acceptance: acc:author-plan-substrate:E002-UNIT-001-canonical-home-and-schema
# WMBT: wmbt:author-plan-substrate:E002
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""E002-UNIT-001 (plan feature) — create_feature writes a schema-valid file at features/<name>.yaml.

RED: create_feature does not exist yet.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml
from jsonschema import validate

from atdd.planner.commands.author import create_feature

_PLAN_SCHEMAS = Path(__file__).resolve().parents[2] / "schemas"


def _plan_schema(kind):
    return json.loads((_PLAN_SCHEMAS / f"{kind}.schema.json").read_text(encoding="utf-8"))


def test_create_feature_writes_canonical_home(tmp_path):
    spec = {
        "urn": "feature:demo-wagon:do-thing",
        "wagon": "wagon:demo-wagon",
        "description": "a demo feature for the create_feature writer test",
        "sizing": {"wmbts": 1, "footprint_score": 4, "footprint_size": "S"},
        "wmbts": ["wmbt:demo-wagon:E001"],
        "components": {"backend": {"application": [
            {"type": "use_cases", "count": 1, "rationale": "the create_feature write path"}]}},
    }
    path = create_feature(spec, root=tmp_path)
    assert path == tmp_path / "plan" / "demo_wagon" / "features" / "do_thing.yaml"
    assert path.exists()
    validate(yaml.safe_load(path.read_text()), _plan_schema("feature"))
