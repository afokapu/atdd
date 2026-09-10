# URN: test:coach:graph-builder:ensure-node-resolves-before-creating
# Issue: #1753 (child of #1733)
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""#1753 — the graph must not invent the nodes it claims to have resolved.

``TraceabilityGraph._ensure_node`` created a node for ANY URN handed to it and
consulted no resolver. ``_build_component_edges`` therefore synthesized **28
phantom feature parents**, and **149 of 170** component->feature edges pointed
at them. The chain read as resolved because the graph had fabricated the far end
moments earlier.

A fabricated node is worse than a missing one: absence is reportable, a
fabricated node reports as resolved. So the contract is three-part, and each
part has a test here:

1. an unresolvable endpoint gets **no node**,
2. it is **recorded** in ``unresolved_references`` — never silently dropped,
3. the **edge survives**, because deleting it would substitute a quieter lie
   for a loud one.
"""
from __future__ import annotations

from atdd.coach.utils.graph.graph_builder import (
    EdgeType,
    TraceabilityGraph,
    URNEdge,
    URNNode,
)

_REAL = "feature:govern-lifecycle:bind-issue-feature"
_FAKE = "feature:govern-lifecycle:does-not-exist-xyz"
_COMPONENT = "component:govern-lifecycle:bind-issue-feature:Thing:backend:domain"


def _resolver_allowing(*resolvable: str):
    """Write-path resolver: None (allow) for the named URNs, a reason otherwise."""

    def reason(urn: str, family: str):
        if urn in resolvable:
            return None
        return f"{family} URN did not resolve: {urn}"

    return reason


def _graph_with(*resolvable: str) -> TraceabilityGraph:
    return TraceabilityGraph(node_resolver=_resolver_allowing(*resolvable))


def _contains(source: str, target: str) -> URNEdge:
    return URNEdge(
        source_urn=source, target_urn=target, edge_type=EdgeType.CONTAINS
    )


def test_unresolvable_endpoint_creates_no_node() -> None:
    """The fault this issue exists for: a URN that resolves to nothing gets no node."""
    graph = _graph_with(_COMPONENT)
    graph.add_edge(_contains(_FAKE, _COMPONENT))

    assert graph.get_node(_FAKE) is None, "graph fabricated a node it never resolved"
    assert _FAKE not in graph.nodes


def test_unresolvable_endpoint_is_recorded_not_dropped() -> None:
    """Refusing to invent must not become refusing to mention."""
    graph = _graph_with(_COMPONENT)
    graph.add_edge(_contains(_FAKE, _COMPONENT))

    unresolved = graph.unresolved_references
    assert _FAKE in unresolved, "unresolvable endpoint vanished without a report"
    assert unresolved[_FAKE].family == "feature"
    assert _FAKE in unresolved[_FAKE].reason


def test_edge_survives_so_the_dangle_stays_visible() -> None:
    """Deleting the edge would be a quieter lie than fabricating the node."""
    graph = _graph_with(_COMPONENT)
    graph.add_edge(_contains(_FAKE, _COMPONENT))

    assert len(graph.edges) == 1, "the dangling edge was silently dropped"
    assert graph.edges[0].source_urn == _FAKE
    # ...and traversal still skips the absent endpoint rather than exploding.
    assert graph.get_parents(_COMPONENT, EdgeType.CONTAINS) == []


def test_resolvable_endpoint_still_gets_its_node() -> None:
    """The fix must not stop the graph creating nodes that genuinely resolve."""
    graph = _graph_with(_REAL, _COMPONENT)
    graph.add_edge(_contains(_REAL, _COMPONENT))

    assert graph.get_node(_REAL) is not None
    assert graph.unresolved_references == {}
    assert [n.urn for n in graph.get_parents(_COMPONENT, EdgeType.CONTAINS)] == [_REAL]


def test_declared_node_is_never_second_guessed() -> None:
    """A node added authoritatively by add_node() is not re-resolved away."""
    graph = _graph_with()  # resolver refuses everything
    graph.add_node(URNNode(urn=_REAL, family="feature"))
    graph.add_edge(_contains(_REAL, _COMPONENT))

    assert graph.get_node(_REAL) is not None, "an already-declared node was discarded"
    assert _REAL not in graph.unresolved_references


def test_no_resolver_preserves_legacy_behaviour() -> None:
    """A graph built without a resolver (get_subgraph copies) is unchanged.

    Those graphs only ever re-add nodes that were already resolved when the
    source graph was built, so re-resolving them would be pure cost.
    """
    graph = TraceabilityGraph()
    graph.add_edge(_contains(_FAKE, _COMPONENT))

    assert graph.get_node(_FAKE) is not None
    assert graph.unresolved_references == {}


def test_ensure_node_is_the_only_edge_endpoint_write_path() -> None:
    """Gate test: no add_edge path may create an endpoint node bypassing _ensure_node.

    Pins the invariant that makes the other tests meaningful — if a second write
    path appeared, fabrication would return through it.
    """
    import inspect

    source = inspect.getsource(TraceabilityGraph.add_edge)
    creations = [
        line for line in source.splitlines()
        if "self._nodes[" in line and "=" in line.split("self._nodes[")[0] + "="
    ]
    assert not creations, f"add_edge writes _nodes directly, bypassing the resolver: {creations}"
    assert source.count("_ensure_node") == 2, (
        "add_edge must route BOTH endpoints through _ensure_node"
    )
