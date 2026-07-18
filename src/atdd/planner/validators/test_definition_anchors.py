# URN: test:author-atdd-substrate:definition-anchor:D001-GREEN-001-core-artifacts-anchored
# Acceptance: acc:author-atdd-substrate:D001-GREEN-001-core-artifacts-anchored
# WMBT: wmbt:author-atdd-substrate:D001
# Phase: GREEN
# Layer: integration
# Runtime: python
# Purpose: Enforce planner.definition.anchor-required — every core planner domain
#          artifact carries a `.definition` advisory semantic anchor (kind: family)
#          that is graph-connected. RED without the anchors; GREEN once authored.
"""planner.definition.anchor-required validator (#1352).

Every core planner domain artifact (theme, train, interlocking, wagon, feature,
wmbt, artifact) MUST have a ``planner.<artifact>.definition`` node that is
``kind: family`` (an advisory semantic anchor) and is graph-connected — referenced
as a source_ref or target_ref of at least one edge in the relationship graph.

Convention: src/atdd/planner/conventions/nodes/planner.definition.anchor-required.convention.yaml
Rule:       planner.definition.anchor-required
Run:        atdd validate planner
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Set

import pytest
import yaml

from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation

pytestmark = [pytest.mark.planner, pytest.mark.platform]

_RULE = bind_rule("planner.definition.anchor-required")
_VALIDATOR_ID = "definition_anchor_required"

REPO = find_repo_root()
NODES = REPO / "src" / "atdd" / "planner" / "conventions" / "nodes"
GRAPH = REPO / "src" / "atdd" / "coach" / "graph" / "relationships.yaml"

# The seven core planner domain-decomposition artifacts (docs discussion / #1352).
CORE_ARTIFACTS = (
    "theme",
    "train",
    "interlocking",
    "wagon",
    "feature",
    "wmbt",
    "artifact",
)


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


def scan_missing_anchors() -> List[Violation]:
    referenced = referenced_node_ids(GRAPH)
    violations: List[Violation] = []
    for artifact in CORE_ARTIFACTS:
        rule_id = f"planner.{artifact}.definition"
        path = NODES / f"{rule_id}.convention.yaml"
        rel = f"src/atdd/planner/conventions/nodes/{rule_id}.convention.yaml"
        if not path.exists():
            violations.append(
                Violation(
                    rule_id=_RULE.rule_id,
                    severity=_RULE.severity,
                    location=f"{rel}:1",
                    detail=f"core artifact {artifact!r} has no definition anchor ({rule_id})",
                )
            )
            continue
        node = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if node.get("kind") != "family":
            violations.append(
                Violation(
                    rule_id=_RULE.rule_id,
                    severity=_RULE.severity,
                    location=f"{rel}:1",
                    detail=(
                        f"definition anchor {rule_id} must be kind:family "
                        f"(advisory semantic anchor), found {node.get('kind')!r}"
                    ),
                )
            )
        if rule_id not in referenced:
            violations.append(
                Violation(
                    rule_id=_RULE.rule_id,
                    severity=_RULE.severity,
                    location=f"{rel}:1",
                    detail=(
                        f"definition anchor {rule_id} is an orphan — not referenced "
                        "as a source_ref/target_ref by any relationship edge"
                    ),
                )
            )
    return violations


def test_every_core_artifact_has_definition_anchor() -> None:
    """Live corpus: every core domain artifact carries a graph-connected family anchor."""
    assert_disposition_satisfied(validator_id=_VALIDATOR_ID, violations=scan_missing_anchors())
