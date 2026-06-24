"""Reusable graph-question archetype for the `schema` family (#1204).

Beyond the template catalogue, this module exposes ``REAL_EVALUATORS`` — the
decentralized, config-parameterized real-graph execution for this family's
templates. The shared evaluator registry (`_support.evaluators`) auto-discovers
this dict and merges it WITHOUT this family editing the central map (#1212
conflict-free fan-out).
"""
from __future__ import annotations

import json

from .._support.template_contract import TemplateContract

TEMPLATES = [
    TemplateContract(
        family_id='schema',
        template_id='node_schema_conformance',
        question='Does each node conform to its declared schema?',
        selector='nodes where node.schema exists',
        traversal='node -> schema_id -> schema document -> validate node payload',
        invariant='jsonschema validation passes',
        auto_capture='a new node is included if it declares `schema`',
        failure_evidence=['node_id', 'schema_id', 'schema_error_path', 'schema_error_message', 'node_location'],
    ),
]

TEMPLATE_IDS = [t.template_id for t in TEMPLATES]


# --- real-graph execution (config-parameterized per variant) ----------------
def _dispatch_map_is_registry(graph) -> list:
    """variant ``schema/dispatch_map_is_registry``: ``plan/_dispatch.yaml`` is a
    DECLARED, schema-valid ``artifact_urn -> train_id`` registry (#1043/#1034).

    Selector  -> the declared dispatch registry document (auto-captured: present
                 only when ``plan/_dispatch.yaml`` exists).
    Traversal -> registry -> declared schema (``plan/_dispatch.schema.json``).
    Invariant -> jsonschema validation passes.
    Evidence  -> a SUBSET of the template's failure_evidence.

    Legacy parity: ``planner/validators/test_dispatch_registry.py`` (same schema,
    same on-disk artifact).
    """
    import jsonschema
    import yaml

    root = graph.root
    rel = "plan/_dispatch.yaml"
    schema_rel = "plan/_dispatch.schema.json"
    dpath = root / rel
    spath = root / schema_rel

    if not dpath.is_file():
        return [{"node_id": rel, "schema_id": "_dispatch",
                 "schema_error_message": "declared dispatch registry is missing",
                 "node_location": rel}]
    if not spath.is_file():
        return [{"node_id": rel, "schema_id": "_dispatch",
                 "schema_error_message": "dispatch registry schema is missing",
                 "node_location": schema_rel}]

    registry = yaml.safe_load(dpath.read_text(encoding="utf-8"))
    schema = json.loads(spath.read_text(encoding="utf-8"))

    out = []
    validator = jsonschema.Draft7Validator(schema)
    for exc in validator.iter_errors(registry):
        out.append({
            "node_id": rel,
            "schema_id": "_dispatch",
            "schema_error_path": "/".join(str(x) for x in exc.absolute_path),
            "schema_error_message": exc.message[:120],
            "node_location": rel,
        })
    return out


def _node_schema_conformance(graph, config=None):
    """Dispatch the ``node_schema_conformance`` template by variant. The default
    (no variant / wagon manifests) delegates to the proven real-graph sentinel;
    ``dispatch_map_is_registry`` routes to the declared-registry schema check."""
    variant = (config or {}).get("variant") if config else None
    if variant == "dispatch_map_is_registry":
        return _dispatch_map_is_registry(graph)
    from .._support import sentinels as S
    return S.node_schema_conformance(graph).violations


REAL_EVALUATORS = {
    "node_schema_conformance": _node_schema_conformance,
}
