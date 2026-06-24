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


EVALUATORS: Dict[str, Callable[[object], List[dict]]] = {
    "direct_reference_resolution": direct_reference_resolution,
    "artifact_reference_resolution": artifact_reference_resolution,
    "reference_chain_resolution": reference_chain_resolution,
    "node_schema_conformance": node_schema_conformance,
    "identifier_grammar_conformance": identifier_grammar_conformance,
    "composed_graph_loads": composed_graph_loads,
    "declaration_to_implementation_binding": declaration_to_implementation_binding,
    "scoped_identifier_uniqueness": scoped_identifier_uniqueness,
}
