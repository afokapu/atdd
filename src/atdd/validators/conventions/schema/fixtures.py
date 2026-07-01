"""Canonical valid/invalid graph fragments for the `schema` family (#1206)."""
from __future__ import annotations

_S = {"id": "s1", "required": ["name"]}
VALID_FRAGMENTS: dict = {
    "node_schema_conformance": {
        "schema_ok": {"nodes": [{"id": "n", "schema": _S, "fields": {"name": "x"}}]},
    },
}
INVALID_FRAGMENTS: dict = {
    "node_schema_conformance": {
        "schema_missing_field": {"nodes": [{"id": "n", "schema": _S, "fields": {}}]},
    },
}
