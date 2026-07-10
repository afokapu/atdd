# URN: test:author-atdd-substrate:author-relationship:C008-UNIT-001-orphan-detection
# Acceptance: acc:author-atdd-substrate:C008-UNIT-001-orphan-detection
# WMBT: wmbt:author-atdd-substrate:C008
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C008-UNIT-001 — the orphan-detection logic flags a node referenced by no edge
and clears a node referenced as either a source_ref or a target_ref."""
from __future__ import annotations

from pathlib import Path

from atdd.planner.validators._orphan_scan import orphan_nodes


def test_unreferenced_node_is_an_orphan() -> None:
    nodes = {"x.area.lonely": Path("x.convention.yaml")}
    assert "x.area.lonely" in orphan_nodes(nodes, referenced=set())


def test_node_referenced_as_source_is_not_orphan() -> None:
    nodes = {"x.area.wired": Path("x.convention.yaml")}
    assert orphan_nodes(nodes, referenced={"x.area.wired"}) == {}


def test_node_referenced_as_target_is_not_orphan() -> None:
    # referenced set already collapses source/target; a node present in it clears
    nodes = {"x.area.target": Path("x.convention.yaml")}
    assert orphan_nodes(nodes, referenced={"x.area.target", "y.other.node"}) == {}


def test_mixed_only_unreferenced_flagged() -> None:
    nodes = {
        "a.one": Path("a.yaml"),
        "b.two": Path("b.yaml"),
        "c.three": Path("c.yaml"),
    }
    orphans = orphan_nodes(nodes, referenced={"a.one", "c.three"})
    assert set(orphans) == {"b.two"}
