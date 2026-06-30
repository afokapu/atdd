# URN: test:author-atdd-substrate:author-convention-node:E007-UNIT-003-graph-loader-exposes-validation
# Acceptance: acc:author-atdd-substrate:E007-UNIT-003-graph-loader-exposes-validation
# WMBT: wmbt:author-atdd-substrate:E007
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""E007-UNIT-003 — the composed graph loader exposes the authored `validation`
block on Node.fields for a single-node convention file."""
from __future__ import annotations

from atdd.planner.commands.author import create_convention_node
from atdd.validators.conventions._support.graph_loader import load_composed_graph

_RID = "planner.train.interlocking-projection-equivalence"
_VALIDATION = {
    "family": "coherence",
    "template": "resolved_fact_agreement",
    "subject_kind": "interlocking",
}


def test_loader_exposes_node_fields_validation(tmp_path):
    # the loader walks <repo_root>/src/atdd, so author the node into that home
    create_convention_node(
        "planner", _RID,
        statement="An interlocking projection must equal its declared route table.",
        terms=[{"term_id": "interlocking", "text": "route-control model"}],
        validation=_VALIDATION,
        root=tmp_path / "src" / "atdd",
    )
    graph = load_composed_graph(tmp_path)
    node = graph.by_id(_RID)
    assert node is not None and node.kind == "rule"
    assert node.fields.get("validation") == _VALIDATION
