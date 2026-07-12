"""Canonical valid/invalid graph fragments for the `uniqueness` family (#1206)."""
from __future__ import annotations

VALID_FRAGMENTS: dict = {
    "scoped_identifier_uniqueness": {
        "unique": {"nodes": [{"id": "x", "scope": "s", "kind": "wmbt"},
                             {"id": "y", "scope": "s", "kind": "wmbt"}]},
    },
}
INVALID_FRAGMENTS: dict = {
    "scoped_identifier_uniqueness": {
        "dup": {"nodes": [{"id": "x", "scope": "s", "kind": "wmbt", "location": "a"},
                          {"id": "x", "scope": "s", "kind": "wmbt", "location": "b"}]},
    },
}
