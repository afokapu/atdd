# Phase: GREEN
# Layer: backend.domain
"""Orphan-node scan helpers for the relationship graph (#1148, extracted #1385).

Every convention node (any ``*.convention.yaml`` carrying a ``rule_id``, test
fixtures and the ``demo.*`` namespace excluded) must appear as a ``source_ref``
or ``target_ref`` of at least one edge in the relationship graph
(``src/atdd/coach/graph/relationships.yaml``). A node referenced by no edge is an
orphan.

Enforcement lives in the convention variant
``validators/conventions/coverage/test_no_orphan_nodes.py``; this module holds the
pure scan functions so they outlive the retired legacy validator
(``planner/validators/test_no_orphan_nodes.py``, #1207 sweep).
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Set

import yaml


def _excluded(path: Path) -> bool:
    s = str(path)
    return "tests/fixtures" in s or "/fixtures/" in s


def node_ids(conv_root: Path) -> Dict[str, Path]:
    """Map every non-fixture convention node rule_id to its file."""
    out: Dict[str, Path] = {}
    for f in conv_root.rglob("*.convention.yaml"):
        if _excluded(f):
            continue
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        rid = data.get("rule_id")
        if rid and not str(rid).startswith("demo."):
            out[str(rid)] = f
    return out


def referenced_node_ids(graph_path: Path) -> Set[str]:
    """Every node id appearing as a source_ref or target_ref in the graph."""
    data = yaml.safe_load(graph_path.read_text(encoding="utf-8")) or {}
    refs: Set[str] = set()
    for edge in data.get("edges", []):
        for key in ("source_ref", "target_ref"):
            val = edge.get(key)
            if val:
                refs.add(str(val).split("#", 1)[0])
    return refs


def orphan_nodes(nodes: Dict[str, Path], referenced: Set[str]) -> Dict[str, Path]:
    """Nodes whose rule_id is referenced by no edge."""
    return {rid: path for rid, path in nodes.items() if rid not in referenced}
