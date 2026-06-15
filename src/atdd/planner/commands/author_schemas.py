# Component: component:author-atdd-substrate:substrate-spine:SchemaRegistry:backend:application
"""Canonical schemas + frozen vocabularies for the author substrate (D001).

Each of the four artifact kinds resolves to exactly one canonical JSON schema
(under ``planner/schemas/author/``) and one canonical home (spec §3). The frozen
controlled vocabularies are a single source of truth shared by the writers and
the schemas — adding a member requires editing the schema (they are *closed*).
"""
from __future__ import annotations

import json
from pathlib import Path

_SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas" / "author"

# kind -> (schema file, canonical home) — spec §3
CANONICAL_KINDS: dict[str, dict[str, str]] = {
    "convention-node": {
        "schema": "convention-node.schema.json",
        "home": "src/atdd/<role>/conventions/nodes/",
    },
    "relationship": {
        "schema": "relationship.schema.json",
        "home": "src/atdd/coach/graph/relationships.yaml",
    },
    "scope": {
        "schema": "scope.schema.json",
        "home": "src/atdd/coach/selectors/scopes.yaml",
    },
    "gate": {
        "schema": "gate.schema.json",
        "home": "src/atdd/coach/gates/",
    },
}


def schema_path(kind: str) -> Path:
    return _SCHEMA_DIR / CANONICAL_KINDS[kind]["schema"]


def load_schema(kind: str) -> dict:
    return json.loads(schema_path(kind).read_text(encoding="utf-8"))


def frozen_vocabularies() -> dict[str, tuple]:
    """Every frozen controlled vocabulary, keyed ``<kind>.<field>``."""
    from atdd.planner.commands.author import KINDS, STATUSES
    from atdd.planner.commands.author_registry import (
        ARTIFACT_KINDS, CONSTRAINTS, CONTROLS, FOUNDATIONS, PLATFORMS,
        RELATIONSHIP_TYPES, RUNTIMES, SELECTION_STRATEGIES, SELECTOR_TYPES,
        STRENGTHS, TRIGGER_NAMES, TRIGGER_TYPES, VIOLATION_ACTIONS,
    )

    return {
        "convention_node.kind": KINDS,
        "convention_node.status": STATUSES,
        "relationship.type": RELATIONSHIP_TYPES,
        "relationship.foundation": FOUNDATIONS,
        "relationship.constraint": CONSTRAINTS,
        "relationship.control": CONTROLS,
        "relationship.strength": STRENGTHS,
        "scope.artifact_kind": ARTIFACT_KINDS,
        "scope.runtime": RUNTIMES,
        "scope.platform": PLATFORMS,
        "scope.selector_type": SELECTOR_TYPES,
        "gate.trigger_type": TRIGGER_TYPES,
        "gate.trigger_name": TRIGGER_NAMES,
        "gate.selection_strategy": SELECTION_STRATEGIES,
        "gate.violation_action": VIOLATION_ACTIONS,
    }
