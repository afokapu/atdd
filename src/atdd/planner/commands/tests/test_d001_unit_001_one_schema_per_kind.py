# URN: test:author-atdd-substrate:substrate-spine:D001-UNIT-001-one-schema-per-kind
# Acceptance: acc:author-atdd-substrate:D001-UNIT-001-one-schema-per-kind
# WMBT: wmbt:author-atdd-substrate:D001
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""D001-UNIT-001 — each kind resolves to exactly one schema and one canonical home."""
from __future__ import annotations

from atdd.planner.commands.author_schemas import CANONICAL_KINDS, schema_path


def test_four_kinds_one_schema_and_home_each():
    assert set(CANONICAL_KINDS) == {"convention-node", "relationship", "scope", "gate"}
    for kind, entry in CANONICAL_KINDS.items():
        assert entry["home"], f"{kind} has no canonical home"
        assert schema_path(kind).exists(), f"{kind} schema file missing: {schema_path(kind)}"
