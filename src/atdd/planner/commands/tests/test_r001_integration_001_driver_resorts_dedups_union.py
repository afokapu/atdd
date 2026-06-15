# URN: test:author-atdd-substrate:author-merge-driver:R001-INTEGRATION-001-driver-resorts-dedups-union
# Acceptance: acc:author-atdd-substrate:R001-INTEGRATION-001-driver-resorts-dedups-union
# WMBT: wmbt:author-atdd-substrate:R001
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""R001-INTEGRATION-001 — the driver re-sorts + dedups the union, no conflict markers."""
from __future__ import annotations

import yaml

from atdd.planner.commands.author_registry import (
    canonical_dump,
    merge_registries,
    relationship_doc,
)


def _edge(src, tgt):
    return {
        "source_ref": src, "type": "enables", "target_ref": tgt,
        "foundation": "finish_to_start", "constraint": "mandatory",
        "control": "internal", "strength": "critical",
    }


def test_driver_unions_dedups_sorts():
    base = canonical_dump(relationship_doc([_edge("coder.green.a", "coder.green.x")]))
    # ours adds 'z', theirs adds 'b'; both keep the shared base edge 'a'
    ours = canonical_dump(relationship_doc([_edge("coder.green.a", "coder.green.x"), _edge("coder.green.z", "coder.green.x")]))
    theirs = canonical_dump(relationship_doc([_edge("coder.green.a", "coder.green.x"), _edge("coder.green.b", "coder.green.x")]))

    merged = merge_registries(base, ours, theirs)

    assert "<<<<<<<" not in merged and ">>>>>>>" not in merged and "=======" not in merged
    doc = yaml.safe_load(merged)
    sources = [e["source_ref"] for e in doc["edges"]]
    # union of {a, z} and {a, b} = {a, b, z}, deduped + sorted
    assert sources == ["coder.green.a", "coder.green.b", "coder.green.z"], sources
    # deterministic: merging again yields identical bytes
    assert merge_registries(base, ours, theirs) == merged
