# URN: test:author-plan-substrate:author-wagon:E001-UNIT-001-canonical-home-and-schema
# Acceptance: acc:author-plan-substrate:E001-UNIT-001-canonical-home-and-schema
# WMBT: wmbt:author-plan-substrate:E001
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""E001-UNIT-001 (plan wagon) — create_wagon writes a schema-valid manifest at the canonical home.

RED: create_wagon does not exist yet.
"""
from __future__ import annotations

from pathlib import Path

import json

import yaml
from jsonschema import validate

from atdd.planner.commands.author import create_wagon

_PLAN_SCHEMAS = Path(__file__).resolve().parents[2] / "schemas"


def _plan_schema(kind):
    return json.loads((_PLAN_SCHEMAS / f"{kind}.schema.json").read_text(encoding="utf-8"))


def test_create_wagon_writes_canonical_home_and_validates(tmp_path):
    spec = {
        "wagon": "demo-wagon",
        "description": "a demo wagon for the create_wagon writer test",
        "subject": "agent:planner",
        "context": "authoring-demo",
        "action": "writes a manifest",
        "goal": "prove the writer works",
        "outcome": "a schema-valid manifest exists",
        "produce": [{"name": "commons:demo:thing"}],
    }
    path = create_wagon(spec, root=tmp_path)
    assert path == tmp_path / "plan" / "demo_wagon" / "_demo_wagon.yaml"
    assert path.exists()
    doc = yaml.safe_load(path.read_text())
    # produce entry gains the schema-required null contract/telemetry keys by construction
    assert doc["produce"][0]["contract"] is None
    assert doc["produce"][0]["telemetry"] is None
    validate(doc, _plan_schema("wagon"))
