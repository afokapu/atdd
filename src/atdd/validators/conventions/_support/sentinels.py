"""Three sentinel validators run against the REAL composed convention graph (#1206).

Each proves a distinct capability end-to-end:
  - theme_must_be_canonical          : node-field inspection (wagon.theme)
  - direct_reference_resolution      : real graph traversal (refs resolve)
  - rule_validator_roundtrip         : rule -> validator -> emitted rule_id roundtrip

Each returns an EvalResult carrying selector cardinality so vacuous passes are
impossible to hide: a variant that selects zero nodes is a failure unless it
explicitly declares an empty selection is expected.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import List

CANONICAL_THEMES = {"commons", "plan", "test", "code", "coach"}


@dataclass
class EvalResult:
    selected_nodes: int = 0
    checked_edges: int = 0
    violations: List[dict] = field(default_factory=list)


def theme_must_be_canonical(graph) -> EvalResult:
    selected = graph.by_kind("wagon")
    r = EvalResult(selected_nodes=len(selected))
    for n in selected:
        r.checked_edges += 1
        if n.theme not in CANONICAL_THEMES:
            r.violations.append({"node_id": n.id, "field": "theme", "value": n.theme,
                                 "grammar_name": "canonical-theme", "node_location": n.location})
    return r


def direct_reference_resolution(graph) -> EvalResult:
    ids = graph.ids()
    selected = [n for n in graph.nodes() if n.refs]
    r = EvalResult(selected_nodes=len(selected))
    for n in selected:
        for ref in graph.refs_from(n):
            r.checked_edges += 1
            if ref not in ids:
                r.violations.append({"source_node": n.id, "ref_field": "refs",
                                     "missing_ref": ref, "source_location": n.location})
    return r


def rule_validator_roundtrip(graph) -> EvalResult:
    selected = [n for n in graph.rules() if n.validator]
    r = EvalResult(selected_nodes=len(selected))
    for rule in selected:
        r.checked_edges += 1
        decl_file = rule.validator.split("::", 1)[0]           # "test_x" or "test_x.py"
        decl_stem = PurePosixPath(decl_file).name.removesuffix(".py")
        emitters = graph.emits(rule.id)                         # files that bind_rule(rule.id)
        emitted_by_decl = any(
            PurePosixPath(e).name.removesuffix(".py") == decl_stem for e in emitters
        )
        if not emitted_by_decl:
            r.violations.append({
                "declaration_id": rule.id,
                "implementation_ref": rule.validator,
                "emitted_identity": sorted(emitters)[:3],
                "actual_resolved_target": "declared validator does not bind_rule(rule.id)",
            })
    return r


def scoped_identifier_uniqueness(graph) -> EvalResult:
    """Rule ids must be globally unique across all convention sources."""
    from collections import defaultdict
    rules = graph.rules()
    r = EvalResult(selected_nodes=len(rules))
    seen = defaultdict(list)
    for n in rules:
        r.checked_edges += 1
        seen[n.id].append(n.location)
    for rid, locs in seen.items():
        if len(locs) > 1:
            r.violations.append({"duplicate_id": rid, "scope": "convention-rules",
                                 "locations": sorted(locs), "node_kinds": ["rule"] * len(locs)})
    return r


def reference_chain_resolution(graph) -> EvalResult:
    """Multi-hop wagon -> feature -> wmbt chains must resolve at every hop."""
    ids = graph.ids()
    wagons = [w for w in graph.by_kind("wagon") if w.refs]
    r = EvalResult(selected_nodes=len(wagons))
    for w in wagons:
        for fref in w.refs:
            r.checked_edges += 1
            feat = graph.by_id(fref)
            if feat is None:
                r.violations.append({"start_node": w.id, "chain_path": [w.id, fref],
                                     "failed_hop": fref, "missing_ref": fref})
                continue
            for wref in graph.refs_from(feat):
                r.checked_edges += 1
                if wref not in ids:
                    r.violations.append({"start_node": w.id,
                                         "chain_path": [w.id, fref, wref],
                                         "failed_hop": wref, "missing_ref": wref})
    return r


SENTINELS = {
    "grammar/theme_must_be_canonical": theme_must_be_canonical,
    "resolution/direct_reference_resolution": direct_reference_resolution,
    "binding/rule_validator_roundtrip": rule_validator_roundtrip,
    "uniqueness/scoped_identifier_uniqueness": scoped_identifier_uniqueness,
    "resolution/reference_chain_resolution": reference_chain_resolution,
}
