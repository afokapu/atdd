# URN: test:coach:traceability_graph:get_subgraph_edge_type_exclude
"""
Regression test for issue #287: TraceabilityGraph.get_subgraph must accept
an `edge_type_exclude` parameter so structural consumers can hide TRAIN_STEP
edges and wagon-rooted subgraphs do not leak cross-train wagons.

Without this filter, once TRAIN_STEP edges exist, a subgraph rooted at a
wagon would pull in every other wagon reachable via a shared handoff from
any train, polluting the structural view. The filter keeps the graph honest
(edges remain first-class) while giving each consumer explicit control.

Rules pinned here:
  - get_subgraph(root, edge_type_exclude={TRAIN_STEP}) does NOT traverse
    TRAIN_STEP edges — their targets are never queued, never added.
  - get_subgraph(root, edge_type_exclude=None) still traverses every edge
    (the existing behavior is preserved as the default).
  - Train-rooted subgraphs with no exclusion contain every TRAIN_STEP edge
    whose owning train matches the root (the journey-mode query).
"""

from __future__ import annotations

import pytest

from atdd.coach.utils.graph.graph_builder import (
    EdgeType,
    TraceabilityGraph,
    URNEdge,
    URNNode,
)


def _make_graph() -> TraceabilityGraph:
    g = TraceabilityGraph()
    # Nodes
    for urn, fam in [
        ("train:0205-renewal", "train"),
        ("train:0105-error", "train"),
        ("wagon:stage", "wagon"),
        ("wagon:dispatch", "wagon"),
        ("wagon:audit", "wagon"),
        ("feature:stage:prep", "feature"),
    ]:
        g.add_node(URNNode(urn=urn, family=fam))

    # INCLUDES: train → wagon
    g.add_edge(URNEdge("train:0205-renewal", "wagon:stage", EdgeType.INCLUDES))
    g.add_edge(URNEdge("train:0205-renewal", "wagon:dispatch", EdgeType.INCLUDES))
    g.add_edge(URNEdge("train:0105-error", "wagon:dispatch", EdgeType.INCLUDES))
    g.add_edge(URNEdge("train:0105-error", "wagon:audit", EdgeType.INCLUDES))

    # TRAIN_STEP: wagon → wagon, labeled by owning train
    g.add_edge(
        URNEdge(
            "wagon:stage",
            "wagon:dispatch",
            EdgeType.TRAIN_STEP,
            metadata={"train": "train:0205-renewal", "step": 2, "category": "alternate"},
        )
    )
    g.add_edge(
        URNEdge(
            "wagon:dispatch",
            "wagon:audit",
            EdgeType.TRAIN_STEP,
            metadata={"train": "train:0105-error", "step": 2, "category": "error"},
        )
    )

    # CONTAINS: wagon → feature
    g.add_edge(URNEdge("wagon:stage", "feature:stage:prep", EdgeType.CONTAINS))
    return g


def test_wagon_rooted_subgraph_excludes_train_step_does_not_leak(_monkey=None):
    g = _make_graph()
    sub = g.get_subgraph(
        "wagon:stage", max_depth=-1, edge_type_exclude={EdgeType.TRAIN_STEP}
    )
    urns = set(sub.nodes.keys())
    assert "wagon:dispatch" not in urns, (
        "TRAIN_STEP edge must not pull in dispatch when excluded"
    )
    assert "wagon:audit" not in urns
    assert "feature:stage:prep" in urns, (
        "CONTAINS edges must still be traversed"
    )
    train_step = [e for e in sub.edges if e.edge_type == EdgeType.TRAIN_STEP]
    assert train_step == [], "Excluded edge type must not appear in subgraph"


def test_wagon_rooted_subgraph_default_leaks_via_train_step_to_show_why_filter_is_needed():
    """
    Baseline: with no exclude, a wagon-rooted subgraph DOES traverse TRAIN_STEP
    edges and pull in cross-train wagons. This test pins the motivation for
    the filter — it proves the default is promiscuous.
    """
    g = _make_graph()
    sub = g.get_subgraph("wagon:stage", max_depth=-1)
    urns = set(sub.nodes.keys())
    assert "wagon:dispatch" in urns, (
        "Without exclude, TRAIN_STEP should still be traversed"
    )


def test_train_rooted_subgraph_contains_its_train_step_edges():
    """
    A subgraph rooted at a train, with no exclusion, must contain every
    TRAIN_STEP edge whose metadata.train matches the root. This is the
    journey-mode query shape.
    """
    g = _make_graph()
    sub = g.get_subgraph("train:0205-renewal", max_depth=-1)
    own_steps = [
        e
        for e in sub.edges
        if e.edge_type == EdgeType.TRAIN_STEP
        and e.metadata.get("train") == "train:0205-renewal"
    ]
    assert len(own_steps) == 1
    assert own_steps[0].source_urn == "wagon:stage"
    assert own_steps[0].target_urn == "wagon:dispatch"


def test_edge_type_exclude_default_preserves_existing_behavior():
    """
    Callers that do not pass edge_type_exclude must see identical behavior
    to the pre-#287 signature — backward-compat guard on the new parameter.
    """
    g = _make_graph()
    a = g.get_subgraph("train:0205-renewal", max_depth=-1)
    b = g.get_subgraph("train:0205-renewal", max_depth=-1, edge_type_exclude=None)
    assert len(a.edges) == len(b.edges)
    assert set(a.nodes.keys()) == set(b.nodes.keys())
