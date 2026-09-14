# URN: test:coach:graph-builder:real-repo-has-no-phantom-features
# Issue: #1753 (child of #1733)
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""#1753 — count the phantom features on the REAL repo, in a test.

The issue's gate test is explicit that "the 28 phantom feature nodes are gone"
must be *counted by a test, not by inspection*, so this builds the actual coach
graph and checks every ``feature:`` node against ``plan/``.

Before the fix the graph carried 198 feature nodes against 170 declared on
disk: 28 invented by ``_ensure_node`` to satisfy component edges whose parent
had never been authored.

The second assertion is the one that keeps this honest. "Zero phantoms" is also
what you get from a graph that found nothing at all, so the test additionally
requires the unresolved set to be NON-empty — the 28 parents must still be
reported, just no longer fabricated. Without that, this test would pass
vacuously, which is the exact failure mode ``#1733`` exists to name.
"""
from __future__ import annotations

import glob

import pytest
import yaml

from atdd.coach.utils.graph.graph_builder import GraphBuilder
from atdd.coach.utils.repo import find_repo_root


@pytest.fixture(scope="module")
def repo_root():
    return find_repo_root()


@pytest.fixture(scope="module")
def graph(repo_root):
    # Disk cache ON: a full build is minutes, and the cache key already tracks
    # every graph input's mtime plus the atdd version.
    return GraphBuilder(repo_root).build()


@pytest.fixture(scope="module")
def declared_features(repo_root) -> set:
    urns = set()
    for path in glob.glob(str(repo_root / "plan" / "*" / "features" / "*.yaml")):
        try:
            data = yaml.safe_load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict) and str(data.get("urn", "")).startswith("feature:"):
            urns.add(data["urn"])
    return urns


def test_no_feature_node_is_absent_from_plan(graph, declared_features) -> None:
    """Every feature node in the graph is authored in plan/ — none invented."""
    assert declared_features, "fixture found no declared features; plan/ unreadable?"

    nodes = {n.urn for n in graph.nodes.values() if n.family == "feature"}
    phantom = sorted(nodes - declared_features)

    assert not phantom, (
        f"{len(phantom)} feature nodes exist that plan/ never declared "
        f"— the graph fabricated them: {phantom[:10]}"
    )


def test_the_unresolved_parents_are_still_reported(graph) -> None:
    """Not fabricating must not mean not mentioning — otherwise this is vacuous.

    The features that used to be fabricated are still referenced by component
    edges, so they must appear in the unresolved set. A zero here would mean
    the dangle became invisible rather than visible.
    """
    unresolved = graph.unresolved_references
    assert unresolved, (
        "no unresolved references recorded — either the corpus became clean or "
        "the dangling parents are being silently dropped instead of reported"
    )

    feature_dangles = [r for r in unresolved.values() if r.family == "feature"]
    assert feature_dangles, (
        "component edges name undeclared feature parents, but none were reported"
    )
    for ref in feature_dangles:
        assert ref.reason, f"{ref.urn} reported with no reason"


def test_component_edges_are_kept_not_deleted(graph) -> None:
    """The edges whose parents do not resolve still exist — a loud dangle."""
    from atdd.coach.utils.graph.graph_builder import EdgeType

    component_edges = [
        e for e in graph.edges
        if e.edge_type == EdgeType.CONTAINS and e.target_urn.startswith("component:")
    ]
    assert component_edges, "feature->component edges vanished entirely"

    nodeless = [e for e in component_edges if e.source_urn not in graph.nodes]
    assert nodeless, (
        "no component edge has a nodeless parent — if the corpus is genuinely "
        "clean this is fine, but it more likely means edges were dropped"
    )
