"""Reusable graph-question archetype for the `acyclicity` family (#1204, #1212).

Real-graph execution: the evaluator runs the template's
``selector -> traversal -> invariant -> evidence`` over the REAL composed
convention graph (``_support.graph_loader.Node`` objects). The only variant,
``no_cross_wagon_consume_cycle``, builds the directed wagon graph from
produce->consume artifact NAMES and rejects any strongly-connected component
spanning more than one wagon — exactly the legacy
``planner.wagon.no-consume-cycle`` semantics, keyed on artifact NAME (never the
nullable ``contract`` field).
"""
from __future__ import annotations

import sys
from typing import Dict, List, Optional, Set

from .._support.template_contract import TemplateContract

TEMPLATES = [
    TemplateContract(
        family_id='acyclicity',
        template_id='forbidden_cycle_absence',
        question='Does a traversal avoid cycles where cycles are forbidden?',
        selector='edge types or relationship subgraphs marked acyclic',
        traversal='nodes -> selected edge type/path -> depth-first traversal',
        invariant='no node appears twice in the same traversal path',
        auto_capture='a new node is included if it participates in an edge type declared acyclic',
        failure_evidence=['cycle_path', 'edge_type', 'start_node', 'repeated_node'],
    ),
]

TEMPLATE_IDS = [t.template_id for t in TEMPLATES]

# Variant -> the edge type whose subgraph must be acyclic. The variant is
# selected by ``config`` (``{"variant": ...}``); a config of None defaults to the
# sole declared variant.
_DEFAULT_VARIANT = 'no_cross_wagon_consume_cycle'
_VARIANT_EDGE_TYPE = {
    'no_cross_wagon_consume_cycle': 'produce->consume',
}


def _wagon_name(node) -> Optional[str]:
    """The wagon's stable name, matching the legacy loader's key derivation
    (``d.get("wagon") or urn.split(":")[-1]``)."""
    return node.fields.get("wagon") or (str(node.id).split(":")[-1] if node.id else None) \
        or node.package


def build_consume_edges(graph) -> Dict[str, Set[str]]:
    """producer-wagon -> {consumer-wagons} via a shared produce/consume artifact NAME.

    Mirrors the legacy ``build_edges``: an edge producer -> consumer exists
    whenever ``consumer`` consumes an artifact NAME that ``producer`` produces
    (self-edges excluded). Keyed on the artifact name, never ``contract``.
    """
    producers: Dict[str, str] = {}
    io: Dict[str, Dict[str, list]] = {}
    for w in graph.by_kind("wagon"):
        name = _wagon_name(w)
        if not name:
            continue
        prod = [p["name"] for p in (w.fields.get("produce") or [])
                if isinstance(p, dict) and p.get("name")]
        cons = [c["name"] for c in (w.fields.get("consume") or [])
                if isinstance(c, dict) and c.get("name")]
        io[name] = {"produce": prod, "consume": cons}
        for pn in prod:
            producers[pn] = name
    edges: Dict[str, Set[str]] = {w: set() for w in io}
    for w, flow in io.items():
        for cn in flow["consume"]:
            pw = producers.get(cn)
            if pw and pw != w:
                edges[pw].add(w)
    return edges


def _cross_wagon_sccs(edges: Dict[str, Set[str]]) -> List[List[str]]:
    """Tarjan SCC over the directed wagon graph; return components of size > 1."""
    index: Dict[str, int] = {}
    low: Dict[str, int] = {}
    onstack: Dict[str, bool] = {}
    stack: List[str] = []
    counter = [0]
    sccs: List[List[str]] = []

    sys.setrecursionlimit(max(10000, sys.getrecursionlimit()))

    def strongconnect(v: str) -> None:
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        onstack[v] = True
        for w in edges.get(v, ()):
            if w not in index:
                strongconnect(w)
                low[v] = min(low[v], low[w])
            elif onstack.get(w):
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp: List[str] = []
            while True:
                w = stack.pop()
                onstack[w] = False
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1:
                sccs.append(sorted(comp))

    for v in list(edges):
        if v not in index:
            strongconnect(v)
    return sccs


def forbidden_cycle_absence(graph, config=None) -> List[dict]:
    """Real-graph evaluator for ``acyclicity/forbidden_cycle_absence``.

    ``config`` selects the variant; only ``no_cross_wagon_consume_cycle`` is
    implemented. Returns one failure-evidence dict per cross-wagon SCC, with
    keys a SUBSET of the template's declared ``failure_evidence``.
    """
    variant = (config or {}).get("variant", _DEFAULT_VARIANT) if isinstance(config, dict) \
        else _DEFAULT_VARIANT
    edge_type = _VARIANT_EDGE_TYPE.get(variant)
    if edge_type is None:
        raise NotImplementedError(f"acyclicity: unknown variant {variant!r}")

    edges = build_consume_edges(graph)
    out: List[dict] = []
    for comp in _cross_wagon_sccs(edges):
        # comp is sorted; the cycle path closes back on its first node.
        out.append({
            "cycle_path": comp + [comp[0]],
            "edge_type": edge_type,
            "start_node": comp[0],
            "repeated_node": comp[0],
        })
    return out


REAL_EVALUATORS = {
    "forbidden_cycle_absence": forbidden_cycle_absence,
}
