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


# Default graph id for the core convention relationship graph (spec §6.1).
DEFAULT_GRAPH_ID = "atdd.convention.relationships"


def relationship_doc(edges: list, graph_id: str = DEFAULT_GRAPH_ID) -> dict:
    return {
        "schema_version": "1.0.0",
        "graph_id": graph_id,
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
    graph_id = doc.get("graph_id", DEFAULT_GRAPH_ID)  # preserve an existing graph id
    edges = [e for e in doc.get("edges", []) if _edge_key(e) != _edge_key(edge)]
    edges.append(edge)
    _atomic_write(path, canonical_dump(relationship_doc(edges, graph_id)))


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


# =============================================================================
# Scope / selector kind (spec §7)
# =============================================================================
ARTIFACT_KINDS = (
    "source_file", "test_file", "plan_file", "contract_file",
    "pull_request", "issue", "remote_resource", "runtime_evidence",
)
RUNTIMES = ("python", "typescript", "supabase", "flutter", None)
PLATFORMS = ("github", "local_fs", "supabase", "vercel", "convex", None)
SELECTOR_TYPES = (
    "path_glob", "git_path_prefix", "header_scan", "manifest_query",
    "github_pr", "github_issue", "remote_resource", "runtime_evidence",
)
_ID_RE = re.compile(r"^[a-z][a-z0-9_-]*(?:\.[a-z0-9_-]+)+$")


def validate_scope(scope: dict) -> None:
    if not _ID_RE.match(scope.get("scope_id", "")):
        raise AuthorInputError("scope_id", f"invalid scope_id {scope.get('scope_id')!r}")
    ak = scope.get("artifact_kind")
    if ak is not None and ak not in ARTIFACT_KINDS:
        raise AuthorInputError("artifact_kind", f"invalid artifact_kind {ak!r}; one of {ARTIFACT_KINDS}")
    if scope.get("runtime") not in RUNTIMES:
        raise AuthorInputError("runtime", f"invalid runtime {scope.get('runtime')!r}; one of {RUNTIMES}")
    if scope.get("platform") not in PLATFORMS:
        raise AuthorInputError("platform", f"invalid platform {scope.get('platform')!r}; one of {PLATFORMS}")
    selectors = scope.get("selectors") or []
    if not selectors:
        raise AuthorInputError("selectors", "a scope must contain at least one selector (§7)")
    for sel in selectors:
        # V1 selector: a discovery mechanism with a stable id + include/exclude.
        if not _ID_RE.match(sel.get("selector_id", "")):
            raise AuthorInputError("selectors", f"invalid selector_id {sel.get('selector_id')!r}")
        if sel.get("type") not in SELECTOR_TYPES:
            raise AuthorInputError("selectors", f"invalid selector type {sel.get('type')!r}; one of {SELECTOR_TYPES}")
        if not (sel.get("include") or []):
            raise AuthorInputError("selectors", f"selector {sel.get('selector_id')!r} needs at least one include pattern")


def scope_doc(scope_id: str, selectors: list, *, artifact_kind=None, runtime=None, platform=None) -> dict:
    """A per-file scope: the surface (scope_id, artifact_kind) + embedded
    selectors (sorted by selector_id)."""
    doc = {"schema_version": "1.0.0", "kind": "scope", "scope_id": scope_id}
    if artifact_kind is not None:
        doc["artifact_kind"] = artifact_kind
    if runtime is not None:
        doc["runtime"] = runtime
    if platform is not None:
        doc["platform"] = platform
    doc["selectors"] = sorted(selectors, key=lambda s: s["selector_id"])
    return doc


def write_scope(scope: dict, path) -> None:
    """Validate + write one per-file scope (selectors embedded, sorted)."""
    validate_scope(scope)
    doc = scope_doc(
        scope["scope_id"], scope["selectors"],
        artifact_kind=scope.get("artifact_kind"),
        runtime=scope.get("runtime"), platform=scope.get("platform"),
    )
    _atomic_write(path, canonical_dump(doc))


def insert_scope_selector(scope_meta: dict, selector: dict, path) -> dict:
    """Add (dedup by selector_id) one selector to the per-file scope at ``path``.

    Loads or creates the scope file, merges scope metadata, dedup-inserts the
    selector, validates the whole scope, and writes it. Returns the scope dict.
    """
    existing = {}
    if os.path.exists(path):
        existing = yaml.safe_load(open(path, encoding="utf-8").read()) or {}
    selectors = [s for s in existing.get("selectors", []) if s.get("selector_id") != selector["selector_id"]]
    selectors.append(selector)
    scope = {"scope_id": scope_meta["scope_id"], "selectors": selectors}
    for key in ("artifact_kind", "runtime", "platform"):
        val = scope_meta.get(key) if scope_meta.get(key) is not None else existing.get(key)
        if val is not None:
            scope[key] = val
    write_scope(scope, path)
    return scope


# =============================================================================
# Gate kind (spec §8)
# =============================================================================
TRIGGER_TYPES = ("git_hook", "ci", "manual_command")
TRIGGER_NAMES = ("post-commit", "pre-push", "pull-request", "ci", "local")
SELECTION_STRATEGIES = ("blast_radius", "full", "phase_subset", "explicit_validators")
VIOLATION_ACTIONS = ("never_block", "block", "warn", "defer_to_ci")


def validate_gate(gate: dict) -> None:
    if not _ID_RE.match(gate.get("gate_id", "")):
        raise AuthorInputError("gate_id", f"invalid gate_id {gate.get('gate_id')!r}")
    trig = gate.get("trigger") or {}
    if trig.get("type") not in TRIGGER_TYPES:
        raise AuthorInputError("trigger", f"invalid trigger type {trig.get('type')!r}; one of {TRIGGER_TYPES}")
    if trig.get("name") not in TRIGGER_NAMES:
        raise AuthorInputError("trigger", f"invalid trigger name {trig.get('name')!r}; one of {TRIGGER_NAMES}")
    sel = gate.get("selection") or {}
    if sel.get("strategy") not in SELECTION_STRATEGIES:
        raise AuthorInputError("selection", f"invalid selection strategy {sel.get('strategy')!r}; one of {SELECTION_STRATEGIES}")
    onv = gate.get("on_violation") or {}
    if onv.get("action") not in VIOLATION_ACTIONS:
        raise AuthorInputError("action", f"invalid violation action {onv.get('action')!r}; one of {VIOLATION_ACTIONS}")
    ex = gate.get("exit") or {}
    if "success_code" not in ex or "failure_code" not in ex:
        raise AuthorInputError("exit", "exit behavior must be explicit (success_code + failure_code, §8)")


def gate_doc(gates: list) -> dict:
    return {
        "schema_version": "1.0.0",
        "kind": "gate_registry",
        "gates": sorted(gates, key=lambda g: g["gate_id"]),
    }


def insert_gate(gate: dict, path) -> None:
    validate_gate(gate)
    if os.path.exists(path):
        doc = yaml.safe_load(open(path, encoding="utf-8").read()) or gate_doc([])
    else:
        doc = gate_doc([])
    gates = [g for g in doc.get("gates", []) if g["gate_id"] != gate["gate_id"]]
    gates.append(gate)
    _atomic_write(path, canonical_dump(gate_doc(gates)))


def gitattributes_lines() -> list[str]:
    """`.gitattributes` lines registering the merge driver for registry files."""
    return [
        f"{_RELATIONSHIPS_HOME} merge={MERGE_DRIVER_NAME}",
        f"{_SCOPES_HOME} merge={MERGE_DRIVER_NAME}",
        f"{_GATES_GLOB} merge={MERGE_DRIVER_NAME}",
    ]
