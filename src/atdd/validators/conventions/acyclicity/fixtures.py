"""Canonical valid/invalid graph fragments for the `acyclicity` family (#1206, #1212).

Fragments are REAL ``ConventionGraph`` objects (not dict fixtures): each is a
tiny composed graph of ``wagon`` nodes carrying ``produce``/``consume`` flows,
adapted INTO the same node model the real loader emits. The evaluator runs
against these exactly as it runs against the composed repo graph.
"""
from __future__ import annotations

from typing import List, Tuple

from .._support.graph_loader import ConventionGraph, Node


def _wagon(name: str, produce: List[str], consume: List[str]) -> Node:
    return Node(
        id=f"wagon:{name}",
        kind="wagon",
        location=f"plan/{name.replace('-', '_')}/_{name.replace('-', '_')}.yaml",
        package=name.replace("-", "_"),
        fields={
            "wagon": name,
            "produce": [{"name": n} for n in produce],
            "consume": [{"name": n} for n in consume],
        },
    )


def _graph(wagons: List[Node]) -> ConventionGraph:
    g = ConventionGraph()
    for w in wagons:
        g._add(w)
    return g


# VALID: an acyclic produce->consume chain (a -> b -> c). No SCC spans >1 wagon.
def _valid_acyclic_chain() -> ConventionGraph:
    return _graph([
        _wagon("acy-a", produce=["x:art:a"], consume=[]),
        _wagon("acy-b", produce=["x:art:b"], consume=["x:art:a"]),
        _wagon("acy-c", produce=[], consume=["x:art:b"]),
    ])


# INVALID: a 2-wagon reciprocal cycle (a produces what b consumes and vice
# versa) — the directed wagon graph has an SCC {acy-a, acy-b}.
def _invalid_two_wagon_cycle() -> ConventionGraph:
    return _graph([
        _wagon("acy-a", produce=["x:art:from-a"], consume=["x:art:from-b"]),
        _wagon("acy-b", produce=["x:art:from-b"], consume=["x:art:from-a"]),
    ])


VALID_FRAGMENTS = {
    "acyclic_chain": _valid_acyclic_chain,
}
INVALID_FRAGMENTS = {
    "two_wagon_cycle": _invalid_two_wagon_cycle,
}


def cycle_members(fragment_factory) -> Tuple[str, ...]:
    """The wagon names expected to form the invalid fragment's cross-wagon SCC."""
    return ("acy-a", "acy-b")
