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
    # train-interlocking entrypoint-shape presence (#1249 / parent #1246). The
    # interlocking artifact declares whether it is runtime-exposed and which
    # Station Master actions reach it; this template asserts the conditional
    # shape (exposed -> actions; not exposed -> reason) is structurally present.
    TemplateContract(
        family_id='schema',
        template_id='required_field_presence',
        question='Does each declaring subject carry the conditionally-required fields its shape demands?',
        selector='subjects that declare a conditional field-presence shape (e.g. interlocking entrypoint)',
        traversal='subject -> declared shape -> required-field set under the active condition',
        invariant='every conditionally-required field is present and non-empty',
        auto_capture='a subject is included only when it declares a shape this template knows',
        failure_evidence=['interlocking_id', 'exposed', 'actions', 'reason', 'field_path'],
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


# NOTE: the schema-family ``required_field_presence`` template (the interlocking
# entrypoint-shape presence rule, #1249) is intentionally NOT exposed in
# ``REAL_EVALUATORS``. The shared evaluator registry (``_support.evaluators``) is
# keyed by template_id alone, and the ``presence`` family already owns a
# ``required_field_presence`` evaluator — registering a second under the same key
# would shadow it. The executable enforcement of the entrypoint-shape rule lives
# in the planner validator ``test_sequence_diagram_sanity`` (via
# ``planner.interlocking.sanity.entrypoint_shape_violations``), which is the
# rule's bound ``implementation.ref``. The TemplateContract above documents the
# template's intent for the registry/roundtrip catalogue.
REAL_EVALUATORS = {
    "node_schema_conformance": _node_schema_conformance,
}
