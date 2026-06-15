# URN: test:author-atdd-substrate:substrate-spine:D001-UNIT-002-schemas-are-self-consistent
# Acceptance: acc:author-atdd-substrate:D001-UNIT-002-schemas-are-self-consistent
# WMBT: wmbt:author-atdd-substrate:D001
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""D001-UNIT-002 — every canonical schema is a valid JSON Schema with a stable $id."""
from __future__ import annotations

from jsonschema import Draft7Validator

from atdd.planner.commands.author_schemas import CANONICAL_KINDS, load_schema


def test_each_schema_is_valid_with_stable_id():
    seen_ids = set()
    for kind in CANONICAL_KINDS:
        schema = load_schema(kind)
        Draft7Validator.check_schema(schema)  # raises if not a valid JSON Schema
        assert schema.get("$id"), f"{kind} schema has no $id"
        assert schema["$id"] not in seen_ids, "schema $id is not unique"
        seen_ids.add(schema["$id"])
