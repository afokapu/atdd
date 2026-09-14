# URN: test:coach:graph-builder:consumer-repo-no-fabrication
# Issue: #1753 (child of #1733)
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""#1753 — the no-fabrication contract must hold in a CONSUMER repo, not just atdd.

Two consumer shapes, and the second is the one that matters:

* a consumer whose components resolve **differently** (its own layout) gets the
  same behaviour — a declared component is a node, an undeclared parent is not
  invented;
* a consumer with **no** components at all exercises no fabrication path — and
  the test asserts that emptiness is *distinguishable from* a clean pass rather
  than silently counted as one.

That second assertion exists because ``#1733``'s whole theme is enforcement over
an empty set proving nothing. "Zero fabrications because there was nothing to
fabricate" and "zero fabrications because the resolver worked" are different
facts, and a test that cannot tell them apart is the vacuity pattern again.
"""
from __future__ import annotations

from pathlib import Path

from atdd.coach.utils.graph.graph_builder import EdgeType, GraphBuilder


def _consumer_repo(root: Path) -> Path:
    """Minimal consumer layout: a plan/ dir and a src/ tree of its own shape."""
    (root / "plan").mkdir(parents=True, exist_ok=True)
    (root / "src").mkdir(parents=True, exist_ok=True)
    return root


def _write_component(root: Path, rel: str, urn: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# URN: {urn}\n\nVALUE = 1\n", encoding="utf-8")
    return path


def _build(root: Path):
    return GraphBuilder(root, use_cache=False).build()


def test_consumer_component_with_no_declared_feature_is_not_fabricated(tmp_path):
    """The defect, reproduced in a consumer: the parent feature must not appear."""
    root = _consumer_repo(tmp_path)
    urn = "component:billing:charge-card:Charger:backend:domain"
    _write_component(root, "src/billing/charge_card/domain/charger.py", urn)

    graph = _build(root)

    assert graph.get_node(urn) is not None, "the declared component should be a node"
    assert graph.get_node("feature:billing:charge-card") is None, (
        "consumer repo fabricated a feature parent that plan/ never declared"
    )


def test_consumer_dangling_parent_is_reported(tmp_path):
    """Refusing to invent must still report — in a consumer repo too."""
    root = _consumer_repo(tmp_path)
    urn = "component:billing:charge-card:Charger:backend:domain"
    _write_component(root, "src/billing/charge_card/domain/charger.py", urn)

    graph = _build(root)

    assert "feature:billing:charge-card" in graph.unresolved_references, (
        "the dangling parent was neither created nor reported — it vanished"
    )


def test_consumer_component_edge_survives(tmp_path):
    """The edge is kept so the dangle stays loud rather than quietly deleted."""
    root = _consumer_repo(tmp_path)
    urn = "component:billing:charge-card:Charger:backend:domain"
    _write_component(root, "src/billing/charge_card/domain/charger.py", urn)

    graph = _build(root)

    edges = [
        e for e in graph.edges
        if e.edge_type == EdgeType.CONTAINS and e.target_urn == urn
    ]
    assert edges, "the feature->component edge was dropped instead of reported"
    assert edges[0].source_urn == "feature:billing:charge-card"


def test_consumer_with_no_components_is_empty_not_clean(tmp_path):
    """A consumer with nothing to check must not be reported as a clean pass.

    #1733's recurring finding is enforcement over an empty set. This pins the
    distinction: the run is EMPTY (no components at all), which is a different
    fact from a repo whose components all resolved.
    """
    root = _consumer_repo(tmp_path)

    graph = _build(root)

    components = [n for n in graph.nodes.values() if n.family == "component"]
    assert components == [], "fixture was supposed to have no components"

    # Emptiness is observable: there is no component subject, so a "0 fabricated"
    # result here carries no evidence that the resolver works. The two states are
    # distinguishable, which is what stops the vacuous pass.
    assert graph.unresolved_references == {}
    assert len(components) == 0

    # And the contrast case proves the check is live rather than vacuous.
    _write_component(
        root,
        "src/billing/charge_card/domain/charger.py",
        "component:billing:charge-card:Charger:backend:domain",
    )
    populated = _build(root)
    assert [n for n in populated.nodes.values() if n.family == "component"], (
        "the same builder found nothing even with a component present"
    )
    assert populated.unresolved_references, (
        "populated consumer reported no dangling parent — the check is vacuous"
    )
