# Phase: RED
# Layer: backend.integration
"""planner.wagon.no-consume-cycle validator (#1145, Phase 1).

Builds the directed wagon graph from produce->consume artifact NAMES across
``plan/<wagon>/_<wagon>.yaml`` and rejects any strongly-connected component
that spans more than one wagon (a cross-wagon dependency cycle). Keyed on the
artifact NAME, never the nullable ``contract`` field.

Convention: src/atdd/planner/conventions/nodes/planner.wagon.no-consume-cycle.convention.yaml
Rule:       planner.wagon.no-consume-cycle
Run:        atdd validate planner
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List

import pytest
import yaml

from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation

pytestmark = [pytest.mark.planner]

_RULE = bind_rule("planner.wagon.no-consume-cycle")
_VALIDATOR_ID = "no_cross_wagon_consume_cycle"

REPO_ROOT = find_repo_root()
PLAN_DIR = REPO_ROOT / "plan"


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


def _scan_live() -> List[Violation]:
    violations: List[Violation] = []
    for comp in find_consume_cycles(load_manifests(PLAN_DIR)):
        w0 = comp[0].replace("-", "_")
        loc = f"plan/{w0}/_{w0}.yaml:1"
        violations.append(
            Violation(
                rule_id=_RULE.rule_id,
                severity=_RULE.severity,
                location=loc,
                detail=f"cross-wagon produce/consume cycle: {' -> '.join(comp)} -> {comp[0]}",
            )
        )
    return violations


def test_no_cross_wagon_consume_cycle() -> None:
    """Live corpus: the cross-wagon produce/consume graph must be a DAG."""
    assert_disposition_satisfied(validator_id=_VALIDATOR_ID, violations=_scan_live())


def test_validator_detects_synthetic_cycle() -> None:
    """RED guard: a 2-wagon produce/consume cycle MUST be detected."""
    manifests = {
        "wagon-a": {"produce": ["x:art:from-a"], "consume": ["x:art:from-b"]},
        "wagon-b": {"produce": ["x:art:from-b"], "consume": ["x:art:from-a"]},
    }
    cycles = find_consume_cycles(manifests)
    assert any(set(c) == {"wagon-a", "wagon-b"} for c in cycles), f"no cycle detected: {cycles}"


def test_validator_passes_on_acyclic_chain() -> None:
    """A producer->consumer chain (no back-edge) yields no SCC>1."""
    manifests = {
        "wagon-a": {"produce": ["x:art:a"], "consume": []},
        "wagon-b": {"produce": [], "consume": ["x:art:a"]},
    }
    assert find_consume_cycles(manifests) == []
