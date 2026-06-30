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


def _interlocking_entrypoint_shape(graph) -> list:
    """variant ``schema/planner_train_interlocking_entrypoint_shape`` (#1249).

    Selector  -> interlocking artifacts under the canonical home (auto-captured:
                 present only when a repo declares interlockings).
    Traversal -> artifact -> entrypoint -> conditional required-field set.
    Invariant -> exposed==true requires >=1 action; exposed==false requires a reason.
    Evidence  -> a SUBSET of the template's failure_evidence.
    """
    from atdd.planner.interlocking import InterlockingError, load_interlocking
    from atdd.planner.interlocking.discovery import iter_interlocking_paths

    root = graph.root
    if root is None:
        return []
    out = []
    for path in iter_interlocking_paths(root):
        try:
            il = load_interlocking(path)
        except InterlockingError as exc:
            # Shape-invalid artifacts fail closed: the entrypoint cannot be read.
            out.append({"interlocking_id": str(path.relative_to(root)),
                        "field_path": "entrypoint", "reason": str(exc)[:160]})
            continue
        ep = il.entrypoint
        if ep.exposed and len(ep.actions) < 1:
            out.append({"interlocking_id": il.interlocking_id, "exposed": True,
                        "actions": list(ep.actions),
                        "field_path": "entrypoint.actions"})
        if not ep.exposed and not ep.reason:
            out.append({"interlocking_id": il.interlocking_id, "exposed": False,
                        "reason": ep.reason, "field_path": "entrypoint.reason"})
    return out


def _required_field_presence(graph, config=None):
    """Dispatch the ``required_field_presence`` template by variant (#1249)."""
    variant = (config or {}).get("variant") if config else None
    if variant == "planner_train_interlocking_entrypoint_shape":
        return _interlocking_entrypoint_shape(graph)
    raise NotImplementedError(
        f"schema/required_field_presence: unknown variant {variant!r}"
    )


REAL_EVALUATORS = {
    "node_schema_conformance": _node_schema_conformance,
    "required_field_presence": _required_field_presence,
}
