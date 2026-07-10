# Phase: GREEN
# Layer: backend.domain
"""Cross-wagon produce/consume graph helpers (#1145, extracted #1385).

Builds the directed wagon graph from produce->consume artifact NAMES across
``plan/<wagon>/_<wagon>.yaml``. Keyed on the artifact NAME, never the nullable
``contract`` field.

Enforcement lives in the convention variant
``validators/conventions/acyclicity/test_no_cross_wagon_consume_cycle.py``; this module
holds the graph builders so they outlive the retired legacy validator (#1207 sweep).
Also imported by the wagon-coupling metrics (``_wagon_metrics``).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List

import yaml


def load_manifests(plan_dir: Path) -> Dict[str, Dict[str, list]]:
    """wagon -> {'produce': [names], 'consume': [names]} from plan/*/_*.yaml."""
    out: Dict[str, Dict[str, list]] = {}
    for mf in sorted(plan_dir.glob("*/_*.yaml")):
        try:
            d = yaml.safe_load(mf.read_text()) or {}
        except Exception:
            continue
        wagon = d.get("wagon") or str(d.get("urn", "")).split(":")[-1]
        if not wagon:
            continue
        prod = [p["name"] for p in (d.get("produce") or []) if isinstance(p, dict) and p.get("name")]
        cons = [c["name"] for c in (d.get("consume") or []) if isinstance(c, dict) and c.get("name")]
        out[wagon] = {"produce": prod, "consume": cons}
    return out


def build_edges(manifests: Dict[str, Dict[str, list]]) -> Dict[str, set]:
    """producer-wagon -> {consumer-wagons} via shared artifact NAME."""
    producers: Dict[str, str] = {}
    for w, io in manifests.items():
        for name in io.get("produce", []):
            producers[name] = w
    edges: Dict[str, set] = {w: set() for w in manifests}
    for w, io in manifests.items():
        for name in io.get("consume", []):
            pw = producers.get(name)
            if pw and pw != w:
                edges[pw].add(w)
    return edges


def find_consume_cycles(manifests: Dict[str, Dict[str, list]]) -> List[List[str]]:
    """Return strongly-connected components of size > 1 (the cross-wagon cycles).

    Tarjan SCC over the directed producer-wagon -> consumer-wagon graph.
    """
    edges = build_edges(manifests)
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
