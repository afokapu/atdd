# URN: test:author-atdd-substrate:author-relationship:C008-SMOKE-001-no-orphan-nodes
# Acceptance: acc:author-atdd-substrate:C008-SMOKE-001-no-orphan-nodes
# WMBT: wmbt:author-atdd-substrate:C008
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Purpose: Enforce that every convention node is referenced in the relationship
#          graph — no orphan nodes. Pairs with the existing forward check
#          (no dangling edges) to make graph integrity bidirectional.
"""planner.relationship.no-orphan-nodes validator (#1148).

Every convention node (any ``*.convention.yaml`` carrying a ``rule_id``, test
fixtures and the ``demo.*`` namespace excluded) must appear as a ``source_ref``
or ``target_ref`` of at least one edge in the relationship graph
(``src/atdd/coach/graph/relationships.yaml``). A node referenced by no edge is an
orphan and is refused — the graph must COVER every node, not merely have no
dangling endpoints.

Convention: src/atdd/planner/conventions/nodes/planner.relationship.no-orphan-nodes.convention.yaml
Rule:       planner.relationship.no-orphan-nodes
Run:        atdd validate planner
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Set

import pytest
import yaml

from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation

pytestmark = [pytest.mark.planner]

_RULE = bind_rule("planner.relationship.no-orphan-nodes")
_VALIDATOR_ID = "no_orphan_nodes"

REPO = find_repo_root()
GRAPH = REPO / "src" / "atdd" / "coach" / "graph" / "relationships.yaml"
CONV_ROOT = REPO / "src" / "atdd"


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


def _scan_live() -> List[Violation]:
    orphans = orphan_nodes(node_ids(CONV_ROOT), referenced_node_ids(GRAPH))
    violations: List[Violation] = []
    for rid, path in sorted(orphans.items()):
        rel = path.relative_to(REPO)
        violations.append(
            Violation(
                rule_id=_RULE.rule_id,
                severity=_RULE.severity,
                location=f"{rel}:1",
                detail=(
                    f"orphan convention node {rid!r} is not referenced as a "
                    "source_ref/target_ref by any relationship edge"
                ),
            )
        )
    return violations


def test_no_orphan_convention_nodes() -> None:
    """Live corpus: every convention node is referenced in the relationship graph."""
    assert_disposition_satisfied(validator_id=_VALIDATOR_ID, violations=_scan_live())
