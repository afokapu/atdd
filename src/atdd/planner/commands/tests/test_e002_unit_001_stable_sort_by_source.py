# URN: test:author-atdd-substrate:author-relationship:E002-UNIT-001-stable-sort-by-source
# Acceptance: acc:author-atdd-substrate:E002-UNIT-001-stable-sort-by-source
# WMBT: wmbt:author-atdd-substrate:E002
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""E002-UNIT-001 — inserting two edges yields a file stable-sorted by the key."""
from __future__ import annotations

import yaml

from atdd.planner.commands.author_registry import insert_relationship


def _edge(src, tgt, typ="enables"):
    return {
        "source_ref": src, "type": typ, "target_ref": tgt,
        "foundation": "finish_to_start", "constraint": "mandatory",
        "control": "internal", "strength": "critical", "reason": "x", "confidence": 1.0,
    }


def test_two_edges_stable_sorted(tmp_path):
    path = tmp_path / "relationships.yaml"
    # insert out of order: 'coder.zzz' before 'coder.aaa'
    insert_relationship(_edge("coder.green.zzz", "coder.green.t1"), path)
    insert_relationship(_edge("coder.green.aaa", "coder.green.t2"), path)
    doc = yaml.safe_load(path.read_text())
    sources = [e["source_ref"] for e in doc["edges"]]
    assert sources == ["coder.green.aaa", "coder.green.zzz"], sources


def test_graph_carries_graph_id_header(tmp_path):
    # spec §6.1: the relationship graph declares graph_id + kind.
    path = tmp_path / "relationships.yaml"
    insert_relationship(_edge("coder.green.aaa", "coder.green.t2"), path)
    doc = yaml.safe_load(path.read_text())
    assert doc["graph_id"] == "atdd.convention.relationships"
    assert doc["kind"] == "relationship_graph"


def test_graph_id_per_context_and_passthrough(tmp_path):
    from atdd.planner.commands.author_context import AuthorContext, relationship_graph_id

    # core graph keeps the canonical id; an extension graph is package-scoped
    assert relationship_graph_id(AuthorContext("core")) == "atdd.convention.relationships"
    assert (relationship_graph_id(AuthorContext("extension", "acme.extension.demo"))
            == "acme.extension.demo.relationships")

    # an explicit graph_id is written for a NEW file (extension graph)
    path = tmp_path / "relationships.yaml"
    insert_relationship(_edge("coder.green.a", "coder.green.b"),
                        path, graph_id="acme.extension.demo.relationships")
    assert yaml.safe_load(path.read_text())["graph_id"] == "acme.extension.demo.relationships"

    # an existing graph's id is never rewritten by a later, different graph_id
    insert_relationship(_edge("coder.green.c", "coder.green.d"),
                        path, graph_id="other.extension.x.relationships")
    assert yaml.safe_load(path.read_text())["graph_id"] == "acme.extension.demo.relationships"
