# Component: component:author-atdd-substrate:author-relationship:RegistryWriter:backend:application
"""Registry-class authoring machinery (relationship/scope/gate).

Unlike convention-nodes (one file per rule_id, conflict-free), the relationship,
scope and gate kinds accumulate many entries in one file. Each writer does
**load → dedup-insert → stable-sort by the canonical key → atomic write**, and a
re-sort/dedup git merge driver (R001) resolves concurrent same-block inserts
deterministically. This module owns that shared machinery; the relationship
writer (E002/C003) is implemented here, scope/gate follow.
"""
from __future__ import annotations

import os
import re

import yaml

# author_registry is imported lazily by author.run(); importing author at module
# top level here is safe (no cycle) and reuses the spine's role/id grammar.
from atdd.planner.commands.author import ROLES, AuthorInputError, _RULE_ID_RE

# Frozen relationship vocabularies (spec §6), consumed not redefined.
RELATIONSHIP_TYPES: tuple[str, ...] = (
    "requires", "blocks", "enables", "follows", "awaits",
    "triggered_by", "starts_with", "runs_alongside", "finishes_with", "relieves",
)
FOUNDATIONS = ("finish_to_start", "start_to_start", "finish_to_finish", "start_to_finish")
CONSTRAINTS = ("mandatory", "discretionary", "conditional")
CONTROLS = ("internal", "external", "autonomous")
STRENGTHS = ("critical", "important", "minor")

MERGE_DRIVER_NAME = "atdd-registry"

_TERM_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# canonical homes for the registry kinds (spec §3)
_RELATIONSHIPS_HOME = "src/atdd/coach/graph/relationships.yaml"
_SCOPES_HOME = "src/atdd/coach/selectors/scopes.yaml"
_GATES_GLOB = "src/atdd/coach/gates/*.yaml"


def _validate_ref(ref: str, field: str) -> None:
    """A ref is ``rule_id`` or ``rule_id#term_id`` (role-prefixed rule_id)."""
    rule_id, sep, term_id = ref.partition("#")
    if not _RULE_ID_RE.match(rule_id) or rule_id.split(".", 1)[0] not in ROLES:
        raise AuthorInputError(field, f"invalid ref {ref!r}; rule_id must be role-prefixed")
    if sep and not _TERM_ID_RE.match(term_id):
        raise AuthorInputError(field, f"invalid ref {ref!r}; term_id must be snake_case")


def _check_enum(edge: dict, key: str, allowed: tuple) -> None:
    if key in edge and edge[key] is not None and edge[key] not in allowed:
        raise AuthorInputError(key, f"invalid {key} {edge[key]!r}; one of {allowed}")


def validate_edge(edge: dict) -> None:
    """Validate a relationship edge against the frozen §6 vocabulary."""
    for field in ("source_ref", "type", "target_ref"):
        if not edge.get(field):
            raise AuthorInputError(field, f"missing required edge field {field!r}")
    _validate_ref(edge["source_ref"], "source_ref")
    _validate_ref(edge["target_ref"], "target_ref")
    if edge["type"] not in RELATIONSHIP_TYPES:
        raise AuthorInputError("type", f"invalid type {edge['type']!r}; one of {RELATIONSHIP_TYPES}")
    _check_enum(edge, "foundation", FOUNDATIONS)
    _check_enum(edge, "constraint", CONSTRAINTS)
    _check_enum(edge, "control", CONTROLS)
    _check_enum(edge, "strength", STRENGTHS)


def _edge_key(edge: dict) -> tuple:
    """Canonical key = dedup key = merge sort key (they MUST match)."""
    return (edge["source_ref"], edge["type"], edge["target_ref"])


def _sorted_edges(edges: list) -> list:
    return sorted(edges, key=_edge_key)


def relationship_doc(edges: list) -> dict:
    return {
        "schema_version": "1.0.0",
        "kind": "relationship_graph",
        "edges": _sorted_edges(edges),
    }


def canonical_dump(doc: dict) -> str:
    """Deterministic serialization: sorted map keys, block style, fixed indent."""
    return yaml.safe_dump(doc, sort_keys=True, default_flow_style=False, width=4096)


def _atomic_write(path, text: str) -> None:
    parent = os.path.dirname(str(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, str(path))


def insert_relationship(edge: dict, path) -> None:
    """Validate + dedup-insert an edge into the registry at ``path`` (atomic)."""
    validate_edge(edge)
    if os.path.exists(path):
        doc = yaml.safe_load(open(path, encoding="utf-8").read()) or relationship_doc([])
    else:
        doc = relationship_doc([])
    edges = [e for e in doc.get("edges", []) if _edge_key(e) != _edge_key(edge)]
    edges.append(edge)
    _atomic_write(path, canonical_dump(relationship_doc(edges)))


def merge_registries(base_text: str, ours_text: str, theirs_text: str) -> str:
    """Re-sort/dedup git merge driver: union ours+theirs edges, dedup by key, sort.

    Produces a deterministic, conflict-marker-free file. ``base_text`` is
    accepted for the git driver protocol but the union of the two sides already
    subsumes additive inserts (the common case for registry authoring).
    """
    def _edges(text):
        return (yaml.safe_load(text) or {}).get("edges", []) if text else []

    merged: dict = {}
    for edge in _edges(ours_text) + _edges(theirs_text):
        merged[_edge_key(edge)] = edge
    return canonical_dump(relationship_doc(list(merged.values())))


def gitattributes_lines() -> list[str]:
    """`.gitattributes` lines registering the merge driver for registry files."""
    return [
        f"{_RELATIONSHIPS_HOME} merge={MERGE_DRIVER_NAME}",
        f"{_SCOPES_HOME} merge={MERGE_DRIVER_NAME}",
        f"{_GATES_GLOB} merge={MERGE_DRIVER_NAME}",
    ]
