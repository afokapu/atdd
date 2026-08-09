# URN: test:coach:graph:synthesized-endpoint-provenance
"""
Acceptance tests for #1758 — an edge endpoint nobody declared is observably undeclared.

The load-bearing acceptance:

    A feature endpoint synthesized by graph construction must never be reported as
    equivalent to a feature independently declared and identity-matched from the
    repository.

Two questions the codebase had collapsed into one, and the collapse is the defect:

- **is it resolvable?** — does a file exist at the URN's expected path
  (``metadata['is_broken']``, filled by resolution).
- **was it declared?** — did any artefact actually declare this URN
  (``metadata['declared']``, stamped at synthesis).

``TraceabilityGraph._ensure_node`` manufactures an endpoint out of *another*
artefact's URN text. On the live corpus 44 nodes arrive that way, and **5 of them
resolve** — legacy ``train:NNNN-slug`` aliases that map through
``plan/_trains/_aliases.yaml`` to real files nobody declared as a node. Stamping only
``is_broken`` would report those 5 as equivalent to declared nodes, which is exactly
the confusion this issue exists to remove. So provenance is the load-bearing
invariant and ``IssueType.UNDECLARED`` is the reporting surface — deliberately
separable, so the acceptance does not depend on the reporting choice.

**Fault injection is over a deep copy of the live graph**, mutated in memory; the
shared module graph is asserted untouched afterwards. This is the same technique the
convention suite uses, but *not* the same helper: ``_support/graph_mutations.clone_graph``
is typed to ``ConventionGraph`` and belongs to the convention suite, and the coach
graph is a different graph (``#1754`` Entry 2 records what conflating them costs), so
this module uses ``copy.deepcopy`` directly rather than importing across that boundary.

**The live-corpus baseline is recorded NON-ZERO and that is deliberate.** Following
``validators/conventions/sizing/test_wagon_separability.py::test_live_corpus_legacy_parity``,
the working advisory precedent in this repo: a clean baseline of zero is NOT the right
invariant, because the 44 synthesized endpoints are a real advisory signal, not false
positives. Nothing here is blocking.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from atdd.coach.utils.graph.graph_builder import (
    EdgeType,
    GraphBuilder,
    TraceabilityGraph,
    URNEdge,
)
from atdd.coach.utils.graph.edge_validator import EdgeValidator, IssueType

# .../src/atdd/coach/utils/graph/tests/this_file.py -> parents[6] is the repo root.
REPO_ROOT = Path(__file__).resolve().parents[6]

# A legacy train alias registered in plan/_trains/_aliases.yaml that RESOLVES to a real
# typed train file but is referenced by nothing, so it is absent from the live graph.
# This is the fault that matters: resolvable, and declared by nothing.
_RESOLVABLE_UNDECLARED = "train:0006-state-projection"

# No alias, no file — the ordinary case, kept alongside so the two populations are
# proven to be reported differently rather than assumed to be.
_UNRESOLVABLE_UNDECLARED = "train:9999-does-not-exist-xyz"


@pytest.fixture(scope="module")
def live():
    """The real repo graph, built once, cache disabled.

    ``use_cache=False`` for two reasons: the pickle at ``.atdd/cache/graph.pickle`` is
    served silently when its key matches, and writing it would make this a test that
    mutates the checkout. Costs one full build (~150s) for the module.

    The root assertion is not ceremony. An earlier draft of this module had
    ``parents[5]`` and so rooted the graph at ``src/``, which has no ``plan/``: the
    build succeeded, produced a graph with no plan artefacts, and **six of these ten
    tests passed vacuously**. A measurement that cannot tell "unconfigured" from
    "clean" is the failure this program exists to name, and it happened here first.
    """
    assert (REPO_ROOT / "plan").is_dir(), (
        f"graph root {REPO_ROOT} has no plan/ — these tests would pass vacuously "
        "against an unconfigured tree"
    )
    builder = GraphBuilder(REPO_ROOT, use_cache=False)
    graph = builder.build()
    assert any(n.family == "feature" for n in graph.nodes.values()), (
        "graph carries no feature nodes — unconfigured, not clean"
    )
    return builder, graph


def _synthesized(graph: TraceabilityGraph):
    return [n for n in graph.nodes.values() if n.metadata.get("declared") is False]


def _undeclared_urns(graph: TraceabilityGraph) -> set:
    return {
        i.urn
        for i in EdgeValidator(graph).find_broken()
        if i.issue_type is IssueType.UNDECLARED
    }


def _broken_urns(graph: TraceabilityGraph) -> set:
    return {
        i.urn
        for i in EdgeValidator(graph).find_broken()
        if i.issue_type is IssueType.BROKEN
    }


# ---------------------------------------------------------------------------
# The invariant, on the live corpus
# ---------------------------------------------------------------------------


def test_live_corpus_surfaces_synthesized_endpoints(live) -> None:
    """HONESTY NOTE: this is an ADVISORY metric with a recorded NON-ZERO baseline.

    A ``test_clean_baseline_is_zero`` would be the wrong invariant here — synthesized
    endpoints genuinely exist on the valid live corpus and are a real signal, not false
    positives (``#1754`` Entry 7: 13 modules define that test, 2 mention advisory, 0
    have both). What is pinned is that the stamp RUNS and surfaces findings; the
    differential lives in the fault-injection tests below.
    """
    _, graph = live
    synthesized = _synthesized(graph)

    assert synthesized, (
        "advisory metric expected to surface synthesized endpoints on the live corpus"
    )


def test_every_node_answers_the_declaredness_question(live) -> None:
    """No node is silent about whether it was declared.

    Before #1758 a synthesized node carried an empty ``metadata`` dict, which is
    indistinguishable from "declared, and we know nothing else about it". Every node
    must now carry either a declaration's resolution block or an explicit
    ``declared: False``.
    """
    _, graph = live

    silent = [n.urn for n in graph.nodes.values() if not n.metadata]

    assert not silent, f"nodes carrying no provenance at all: {sorted(silent)[:10]}"


def test_synthesized_endpoint_is_never_equivalent_to_a_declared_one(live) -> None:
    """The load-bearing acceptance, stated as a partition of the node set.

    Every synthesized endpoint is distinguishable from every declared node by a field
    that does not depend on whether a file happens to exist.
    """
    _, graph = live

    synthesized = {n.urn for n in _synthesized(graph)}
    declared = {
        n.urn for n in graph.nodes.values() if n.metadata.get("declared") is not False
    }

    assert synthesized, "no synthesized endpoints to compare"
    assert declared, "no declared nodes to compare"
    assert not (synthesized & declared), (
        "a node read as both synthesized and declared: "
        f"{sorted(synthesized & declared)[:10]}"
    )


def test_a_resolvable_endpoint_is_still_marked_undeclared(live) -> None:
    """The case ``is_broken`` cannot reach, and the reason provenance is load-bearing.

    Regression guard for the 5 legacy train aliases: they resolve to real files, so
    ``is_broken`` is False for every one of them, and a resolvability-only stamp would
    have reported them as equivalent to declared nodes. If this population ever empties,
    the assertion below fails loudly rather than passing vacuously.
    """
    _, graph = live

    resolvable_but_undeclared = [
        n for n in _synthesized(graph) if not n.metadata.get("is_broken")
    ]

    assert resolvable_but_undeclared, (
        "no resolvable-but-undeclared endpoint on the live corpus — this test can no "
        "longer prove that provenance reaches a case is_broken cannot"
    )
    for node in resolvable_but_undeclared:
        assert node.metadata["declared"] is False
        assert node.artifact_path is not None, (
            f"{node.urn} was classified resolvable but carries no artifact_path"
        )


def test_both_populations_are_reported_and_are_reported_differently(live) -> None:
    """Undeclared-and-resolvable reports UNDECLARED; undeclared-and-unresolvable reports
    BROKEN. Neither population is silent, and no node is double-reported."""
    _, graph = live

    undeclared = _undeclared_urns(graph)
    broken = _broken_urns(graph)
    synthesized = {n.urn for n in _synthesized(graph)}

    assert synthesized <= (undeclared | broken), (
        "synthesized endpoints reaching no reporting surface: "
        f"{sorted(synthesized - (undeclared | broken))[:10]}"
    )
    assert not (undeclared & broken), (
        f"double-reported URNs: {sorted(undeclared & broken)[:10]}"
    )
    assert undeclared, "the resolvable-but-undeclared population reports nowhere"


# ---------------------------------------------------------------------------
# Fault injection, over a clone
# ---------------------------------------------------------------------------


def _inject_endpoint(builder: GraphBuilder, graph: TraceabilityGraph, urn: str):
    """Name ``urn`` as an edge source on a DEEP COPY, then run the real post-pass.

    This is the live defect's exact shape: the 5 legacy train aliases became nodes
    because a test header named them as the source of a TESTED_BY edge while no plan
    artefact declared them.
    """
    clone = copy.deepcopy(graph)
    victim = next(n.urn for n in clone.nodes.values() if n.family == "test")

    clone.add_edge(
        URNEdge(
            source_urn=urn,
            target_urn=victim,
            edge_type=EdgeType.TESTED_BY,
            metadata={"source": "fault-injection"},
        )
    )
    builder._stamp_synthesized_endpoints(clone)
    return clone


def test_fault_injection_resolvable_endpoint_raises_the_undeclared_count(live) -> None:
    """A synthetic endpoint that RESOLVES must still raise the undeclared count.

    This is the case a resolvability-only stamp would have missed entirely: the URN
    resolves through the legacy alias map, so ``is_broken`` is False and ``find_broken``
    would never have reached it.
    """
    builder, graph = live
    before = _undeclared_urns(graph)
    assert _RESOLVABLE_UNDECLARED not in before

    clone = _inject_endpoint(builder, graph, _RESOLVABLE_UNDECLARED)
    after = _undeclared_urns(clone)

    assert after == before | {_RESOLVABLE_UNDECLARED}, (
        f"expected exactly one new undeclared endpoint, got {after ^ before}"
    )

    node = clone.nodes[_RESOLVABLE_UNDECLARED]
    assert node.metadata["declared"] is False
    assert node.metadata["is_broken"] is False, (
        "fault is only meaningful if the injected endpoint genuinely resolves"
    )
    assert node.artifact_path is not None

    # The shared graph never saw the fault.
    assert _RESOLVABLE_UNDECLARED not in graph.nodes
    assert _undeclared_urns(graph) == before


def test_fault_injection_unresolvable_endpoint_raises_the_broken_count(live) -> None:
    """A synthetic endpoint that resolves nowhere reports BROKEN, not UNDECLARED —
    the stronger and more actionable statement — and is not reported twice."""
    builder, graph = live
    broken_before = _broken_urns(graph)
    undeclared_before = _undeclared_urns(graph)

    clone = _inject_endpoint(builder, graph, _UNRESOLVABLE_UNDECLARED)

    assert _broken_urns(clone) == broken_before | {_UNRESOLVABLE_UNDECLARED}
    assert _undeclared_urns(clone) == undeclared_before
    assert clone.nodes[_UNRESOLVABLE_UNDECLARED].metadata["declared"] is False

    # The shared graph never saw the fault.
    assert _UNRESOLVABLE_UNDECLARED not in graph.nodes
    assert _broken_urns(graph) == broken_before


def test_fault_injection_does_not_mutate_the_shared_graph(live) -> None:
    """Belt and braces: node/edge counts and the synthesized set survive both faults."""
    builder, graph = live
    nodes_before, edges_before = len(graph.nodes), len(graph.edges)
    synthesized_before = {n.urn for n in _synthesized(graph)}

    _inject_endpoint(builder, graph, _RESOLVABLE_UNDECLARED)
    _inject_endpoint(builder, graph, _UNRESOLVABLE_UNDECLARED)

    assert (len(graph.nodes), len(graph.edges)) == (nodes_before, edges_before)
    assert {n.urn for n in _synthesized(graph)} == synthesized_before


# ---------------------------------------------------------------------------
# The stamp holds without a registry
# ---------------------------------------------------------------------------


def test_stamp_holds_on_a_graph_built_without_a_registry() -> None:
    """``_ensure_node`` stamps provenance with no resolver in reach.

    This is why the stamp lives on ``TraceabilityGraph`` and resolution lives on
    ``GraphBuilder``: the invariant must not be conditional on a registry being
    present, or it would silently lapse for every bare ``TraceabilityGraph()``.
    """
    graph = TraceabilityGraph()

    graph.add_edge(
        URNEdge(
            source_urn="feature:nowhere:invented",
            target_urn="component:nowhere:invented:thing:backend:domain",
            edge_type=EdgeType.CONTAINS,
        )
    )

    for urn in ("feature:nowhere:invented", "component:nowhere:invented:thing:backend:domain"):
        assert graph.nodes[urn].metadata["declared"] is False
        assert graph.nodes[urn].metadata["synthesized_by"] == "graph.add_edge"

    # No resolution has run, so nothing claims the endpoint is broken *or* fine.
    assert "is_broken" not in graph.nodes["feature:nowhere:invented"].metadata


def test_a_declared_node_is_not_stamped_undeclared(live) -> None:
    """The stamp is not applied to nodes built from real declarations."""
    _, graph = live

    declared_feature = next(
        n for n in graph.nodes.values()
        if n.family == "feature" and n.metadata.get("declared") is not False
    )

    assert "declared" not in declared_feature.metadata
    assert declared_feature.metadata.get("source_path")
