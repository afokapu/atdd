"""Canonical valid/invalid graph fragments for the `binding` family (#1206)."""
from __future__ import annotations

VALID_FRAGMENTS: dict = {
    "declaration_to_implementation_binding": {
        "bound": {"nodes": [{"id": "rule", "enforcement": "validator",
                             "implementation_ref": "impl1"},
                            {"id": "impl1", "kind": "implementation"}]},
    },
}
INVALID_FRAGMENTS: dict = {
    "declaration_to_implementation_binding": {
        "unbound": {"nodes": [{"id": "rule", "enforcement": "validator",
                               "implementation_ref": "missing_impl"}]},
    },
}
