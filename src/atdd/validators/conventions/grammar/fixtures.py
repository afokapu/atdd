"""Canonical valid/invalid graph fragments for the `grammar` family (#1206)."""
from __future__ import annotations

_G = {"name": "urn", "pattern": r"[a-z]+:[a-z][a-z0-9-]*", "field": "id"}
VALID_FRAGMENTS: dict = {
    "identifier_grammar_conformance": {
        "id_ok": {"nodes": [{"id": "wagon:foo-bar", "grammar": _G}]},
    },
}
INVALID_FRAGMENTS: dict = {
    "identifier_grammar_conformance": {
        "id_bad": {"nodes": [{"id": "WAGON BAD", "grammar": _G}]},
    },
}
