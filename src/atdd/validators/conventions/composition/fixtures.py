"""Canonical valid/invalid graph fragments for the `composition` family (#1206)."""
from __future__ import annotations

VALID_FRAGMENTS: dict = {
    "composed_graph_loads": {
        "loads": {"nodes": [{"id": "n", "kind": "wagon"}]},
    },
}
INVALID_FRAGMENTS: dict = {
    "composed_graph_loads": {
        "parse_fail": {"nodes": [{"id": "n", "source_file": "bad.yaml",
                                  "parse_error": "yaml parse failed"}]},
    },
}
