"""Reusable graph-question archetype for the `resolution` family (#1204)."""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

import yaml

from .._support import sentinels as S
from .._support.template_contract import TemplateContract

TEMPLATES = [
    TemplateContract(
        family_id='resolution',
        template_id='direct_reference_resolution',
        question='Does every declared reference resolve to an existing graph target?',
        selector='nodes with refs/node_refs/rule_refs/relationship_targets',
        traversal='source node -> reference value -> target index',
        invariant='target_index.contains(reference)',
        auto_capture='a new node is included if it declares references using standard ref fields',
        failure_evidence=['source_node', 'ref_field', 'missing_ref', 'expected_target_kind', 'source_location'],
    ),
    TemplateContract(
        family_id='resolution',
        template_id='artifact_reference_resolution',
        question='Does every file, schema, fixture, or URN artifact reference resolve to a real artifact?',
        selector='nodes with artifact_refs/file_refs/schema_refs/fixture_refs',
        traversal='node -> artifact reference -> repository artifact index',
        invariant='artifact exists and is addressable from repo root/package root',
        auto_capture='a new node is included if it declares artifact references with standard metadata',
        failure_evidence=['node_id', 'artifact_ref', 'artifact_kind', 'expected_path', 'node_location'],
    ),
    TemplateContract(
        family_id='resolution',
        template_id='reference_chain_resolution',
        question='Does a multi-hop reference chain resolve completely?',
        selector='nodes that declare chained references or transitive dependencies',
        traversal='start node -> ref A -> target node -> ref B -> final target',
        invariant='all hops resolve; no missing intermediate target',
        auto_capture='a new node is included if it declares a chain shape using standard traversal metadata',
        failure_evidence=['start_node', 'chain_path', 'failed_hop', 'missing_ref'],
    ),
]

TEMPLATE_IDS = [t.template_id for t in TEMPLATES]


# ---------------------------------------------------------------------------
# Variant-specific real-graph evaluators (#1212 variant wiring).
#
# A few `resolution` variants need template behaviour the foundation evaluator
# does not yet cover, because their LEGACY counterpart reads a DIFFERENT
# representation of the same "does this reference resolve?" question:
#
#   - plan_urn_resolution      : contract URNs in wagon `produce` -> contracts/ dir
#                                (legacy test_plan_urn_resolution reads produce URNs,
#                                 not the node.references docs the default sentinel reads).
#   - draft_wagon_registry     : registry `consume.from: wagon:<slug>` -> registry slug set
#                                (legacy test_draft_wagon_registry reads plan/_wagons.yaml).
#
# Exposing them via REAL_EVALUATORS keeps the central evaluator map untouched
# (decentralised, conflict-free fan-out per `_support.evaluators._real_evaluators`).
# Evidence keys are a SUBSET of the `artifact_reference_resolution` failure_evidence
# (node_id / artifact_ref / artifact_kind / expected_path / node_location).
# ---------------------------------------------------------------------------
def _parse_urn(urn: str) -> Optional[Tuple[str, ...]]:
    """Split a URN the way legacy test_plan_urn_resolution.parse_urn does:
    both ':' and '.' open a path level. Returns None for malformed URNs."""
    if not isinstance(urn, str):
        return None
    parts = urn.split(":", 1)
    if len(parts) < 2:
        return None
    segments = re.split(r"[:\.]", parts[1])
    if len(segments) < 2:
        return None
    return tuple([parts[0]] + segments)


def _contract_urn_resolution(graph) -> List[dict]:
    """`plan_urn_resolution`: every contract URN declared in a wagon `produce`
    item must resolve to a real contracts/ directory (resource- OR domain-level),
    mirroring legacy SPEC-PLATFORM-URN-0001 exactly."""
    contracts_dir = graph.root / "contracts"
    out: List[dict] = []
    for w in graph.by_kind("wagon"):
        for item in (w.fields.get("produce") or []):
            if not isinstance(item, dict):
                continue
            urn = item.get("contract")
            if not urn:
                continue
            parts = _parse_urn(urn)
            if parts is None:
                continue
            path_parts = parts[1:]
            expected = contracts_dir.joinpath(*path_parts)
            domain = contracts_dir / path_parts[0] if path_parts else None
            if not (expected.exists() or (domain and domain.exists())):
                out.append({"node_id": w.id, "artifact_ref": urn,
                            "artifact_kind": "contract",
                            "expected_path": str(expected.relative_to(graph.root)),
                            "node_location": w.location})
    return out


def _registry_consume_resolution(graph) -> List[dict]:
    """`draft_wagon_registry`: every `consume.from: wagon:<slug>` reference in
    plan/_wagons.yaml must resolve to a wagon present in that same registry,
    mirroring legacy SPEC-PLATFORM-REGISTRY-0004 exactly."""
    registry = graph.root / "plan" / "_wagons.yaml"
    out: List[dict] = []
    if not registry.exists():
        return out
    data = yaml.safe_load(registry.read_text(encoding="utf-8")) or {}
    wagons = data.get("wagons", []) or []
    slugs = {w.get("wagon") for w in wagons if isinstance(w, dict) and w.get("wagon")}
    for w in wagons:
        if not isinstance(w, dict):
            continue
        slug = w.get("wagon", "")
        for item in (w.get("consume") or []):
            if not isinstance(item, dict):
                continue
            from_ref = item.get("from", "")
            if isinstance(from_ref, str) and from_ref.startswith("wagon:"):
                referenced = from_ref.split(":", 1)[1]
                if referenced not in slugs:
                    out.append({"node_id": slug, "artifact_ref": from_ref,
                                "artifact_kind": "wagon",
                                "expected_path": referenced,
                                "node_location": "plan/_wagons.yaml"})
    return out


def _artifact_reference_resolution(graph, config=None) -> List[dict]:
    """Variant-aware dispatch for the artifact_reference_resolution template.
    Non-special variants fall back to the canonical foundation sentinel so the
    family's other variants (e.g. plan_cross_refs) are unaffected."""
    variant = (config or {}).get("variant") if config else None
    if variant == "plan_urn_resolution":
        return _contract_urn_resolution(graph)
    if variant == "draft_wagon_registry":
        return _registry_consume_resolution(graph)
    return S.artifact_reference_resolution(graph).violations


# Auto-discovered by `_support.evaluators._real_evaluators` (no central-map edit).
REAL_EVALUATORS = {
    "artifact_reference_resolution": _artifact_reference_resolution,
}
