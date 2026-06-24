"""Canonical valid/invalid graph fragments for the `resolution` family (#1206).

Keyed by template_id. A fragment is {"nodes": [...], "artifacts": [...]}.
"""
from __future__ import annotations

VALID_FRAGMENTS: dict = {
    "direct_reference_resolution": {
        "resolves": {"nodes": [{"id": "a", "refs": ["b"]}, {"id": "b"}]},
    },
    "artifact_reference_resolution": {
        "artifact_present": {"nodes": [{"id": "a", "artifact_refs": ["c.yaml"]}],
                             "artifacts": ["c.yaml"]},
    },
    "reference_chain_resolution": {
        "chain_ok": {"nodes": [{"id": "a", "chain": ["b", "c"]}, {"id": "b"}, {"id": "c"}]},
    },
}
INVALID_FRAGMENTS: dict = {
    "direct_reference_resolution": {
        "dangling_ref": {"nodes": [{"id": "a", "refs": ["ghost"]}]},
    },
    "artifact_reference_resolution": {
        "artifact_missing": {"nodes": [{"id": "a", "artifact_refs": ["missing.yaml"]}],
                             "artifacts": []},
    },
    "reference_chain_resolution": {
        "chain_broken": {"nodes": [{"id": "a", "chain": ["b", "gone"]}, {"id": "b"}]},
    },
}
