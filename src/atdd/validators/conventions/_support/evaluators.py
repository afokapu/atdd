"""Executable graph-question evaluators for the convention validator templates (#1206).

Each evaluator implements one template's ``selector -> traversal -> invariant ->
failure evidence``. Input ``graph`` is either a composed graph (object with a
``.nodes`` list) or a fixture fragment (a dict ``{"nodes": [...], "artifacts": [...]}``).
Output is a list of evidence dicts whose keys are a SUBSET of the template's
declared ``failure_evidence``.

Selectors are metadata-driven (auto-capture): a node participates only if it
declares the relevant field, so a fragment is silently ignored by templates it
does not opt into.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Callable, Dict, List


def _nodes(graph) -> List[dict]:
    if isinstance(graph, dict):
        return list(graph.get("nodes") or [])
    return list(getattr(graph, "nodes", []) or [])


def _artifacts(graph) -> set:
    if isinstance(graph, dict):
        return set(graph.get("artifacts") or [])
    return set(getattr(graph, "artifacts", []) or [])


# --- resolution -------------------------------------------------------------
def direct_reference_resolution(graph) -> List[dict]:
    nodes = _nodes(graph)
    ids = {n.get("id") for n in nodes}
    out = []
    for n in nodes:
        for ref in n.get("refs", []) or []:
            if ref not in ids:
                out.append({"source_node": n.get("id"), "ref_field": "refs",
                            "missing_ref": ref, "source_location": n.get("location")})
    return out


def artifact_reference_resolution(graph) -> List[dict]:
    nodes, arts = _nodes(graph), _artifacts(graph)
    out = []
    for n in nodes:
        for a in n.get("artifact_refs", []) or []:
            if a not in arts:
                out.append({"node_id": n.get("id"), "artifact_ref": a,
                            "expected_path": a, "node_location": n.get("location")})
    return out


def reference_chain_resolution(graph) -> List[dict]:
    nodes = _nodes(graph)
    ids = {n.get("id") for n in nodes}
    out = []
    for n in nodes:
        chain = n.get("chain")
        if not chain:
            continue
        for hop in chain:
            if hop not in ids:
                out.append({"start_node": n.get("id"), "chain_path": chain,
                            "failed_hop": hop, "missing_ref": hop})
                break
    return out


# --- schema -----------------------------------------------------------------
def node_schema_conformance(graph) -> List[dict]:
    out = []
    for n in _nodes(graph):
        schema = n.get("schema")
        if not schema:
            continue
        fieldvals = n.get("fields", {}) or {}
        for req in schema.get("required", []) or []:
            if req not in fieldvals:
                out.append({"node_id": n.get("id"), "schema_id": schema.get("id"),
                            "schema_error_path": req,
                            "schema_error_message": "missing required field",
                            "node_location": n.get("location")})
    return out


# --- grammar ----------------------------------------------------------------
def identifier_grammar_conformance(graph) -> List[dict]:
    out = []
    for n in _nodes(graph):
        gr = n.get("grammar")
        if not gr:
            continue
        field = gr.get("field", "id")
        value = n.get(field, n.get("id"))
        if value is None or not re.fullmatch(gr["pattern"], str(value)):
            out.append({"node_id": n.get("id"), "field": field, "value": value,
                        "grammar_name": gr.get("name"), "parse_error": "does not match grammar"})
    return out


# --- composition ------------------------------------------------------------
def composed_graph_loads(graph) -> List[dict]:
    out = []
    for n in _nodes(graph):
        if n.get("parse_error"):
            out.append({"source_file": n.get("source_file"), "parse_error": n["parse_error"],
                        "node_id_if_available": n.get("id"), "package_id": n.get("package_id")})
    return out


# --- binding ----------------------------------------------------------------
def declaration_to_implementation_binding(graph) -> List[dict]:
    nodes = _nodes(graph)
    impls = {n.get("id") for n in nodes if n.get("kind") == "implementation"}
    out = []
    for n in nodes:
        if n.get("enforcement") != "validator":
            continue
        ref = n.get("implementation_ref")
        if not ref or ref not in impls:
            out.append({"declaration_node": n.get("id"), "implementation_ref": ref,
                        "missing_or_incompatible_implementation": ref,
                        "declaration_location": n.get("location")})
    return out


# --- uniqueness -------------------------------------------------------------
def scoped_identifier_uniqueness(graph) -> List[dict]:
    seen: Dict[tuple, list] = defaultdict(list)
    for n in _nodes(graph):
        if n.get("id") and n.get("scope"):
            seen[(n["scope"], n["id"])].append(n)
    out = []
    for (scope, ident), ns in seen.items():
        if len(ns) > 1:
            out.append({"duplicate_id": ident, "scope": scope,
                        "locations": [x.get("location") for x in ns],
                        "node_kinds": [x.get("kind") for x in ns]})
    return out


# ---------------------------------------------------------------------------
# CANONICAL execution: the real composed graph (graph_loader Node objects).
# `EVALUATORS[template_id](graph, config)` runs selector -> traversal -> invariant
# over the real graph and returns failure-evidence dicts. The proven real-graph
# logic lives in `_support.sentinels`; these adapters expose it template-keyed.
# ---------------------------------------------------------------------------
def _real(sentinel_fn):
    def _run(graph, config=None):
        return sentinel_fn(graph).violations
    return _run


# Families whose archetype.py may expose `REAL_EVALUATORS = {template_id: fn(graph, config)}`.
# Discovery is decentralized so parallel workers each add their family's evaluator
# WITHOUT editing this shared map (conflict-free fan-out).
_FAMILIES = ("presence", "uniqueness", "resolution", "schema", "grammar", "composition",
             "coverage", "sizing", "coherence", "acyclicity", "boundary", "policy", "binding")


def _real_evaluators() -> Dict[str, Callable]:
    from . import sentinels as S
    reg: Dict[str, Callable] = {
        "identifier_grammar_conformance": _real(S.identifier_grammar_conformance),
        "scoped_identifier_uniqueness": _real(S.scoped_identifier_uniqueness),
        "node_schema_conformance": _real(S.node_schema_conformance),
        "direct_reference_resolution": _real(S.direct_reference_resolution),
        "artifact_reference_resolution": _real(S.artifact_reference_resolution),
        "reference_chain_resolution": _real(S.reference_chain_resolution),
        "declaration_to_implementation_binding": _real(S.declaration_to_implementation_binding),
        "composed_graph_loads": _real(S.composed_graph_loads),
        "emitted_identity_roundtrip": _real(S.rule_validator_roundtrip),
    }
    import importlib
    for fam in _FAMILIES:
        try:
            mod = importlib.import_module(f"atdd.validators.conventions.{fam}.archetype")
        except Exception:
            continue
        fam_reg = getattr(mod, "REAL_EVALUATORS", None)
        if isinstance(fam_reg, dict):
            reg.update(fam_reg)  # family-declared evaluators override/extend the built-ins
    return reg


# TRANSITIONAL: the dict-fragment evaluators above. Used only by family fixtures
# that have not yet been migrated to the real-graph model. Removed per-template as
# each family's fixtures.py adopts real-graph fragments (#1212 decommission build).
_DICT_EVALUATORS: Dict[str, Callable[[object], List[dict]]] = {
    "direct_reference_resolution": direct_reference_resolution,
    "artifact_reference_resolution": artifact_reference_resolution,
    "reference_chain_resolution": reference_chain_resolution,
    "node_schema_conformance": node_schema_conformance,
    "identifier_grammar_conformance": identifier_grammar_conformance,
    "composed_graph_loads": composed_graph_loads,
    "declaration_to_implementation_binding": declaration_to_implementation_binding,
    "scoped_identifier_uniqueness": scoped_identifier_uniqueness,
}

# Back-compat alias (was the only registry); now the transitional dict path.
EVALUATORS = _DICT_EVALUATORS


def evaluate(template_id: str, graph, config=None) -> List[dict]:
    """Dispatch a template's execution. The real composed graph is canonical;
    a dict fragment routes to the transitional fixture path until that family's
    fixtures are migrated to the real-graph model."""
    from .graph_loader import ConventionGraph

    if isinstance(graph, ConventionGraph):
        fn = _real_evaluators().get(template_id)
        if fn is None:
            raise NotImplementedError(
                f"no real-graph evaluator implemented for template {template_id!r}"
            )
        return fn(graph, config)

    fn = _DICT_EVALUATORS.get(template_id)
    if fn is None:
        raise NotImplementedError(f"no evaluator implemented for template {template_id!r}")
    return fn(graph)
