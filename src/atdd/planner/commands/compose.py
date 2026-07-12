# Component: component:author-atdd-substrate:package-composition:Compose:backend:application
"""Package discovery + protocol-view composition (#1130, #1133).

The consumption counterpart to the ``author_*`` substrate. Discovers installed
extension/workspace packages, validates their manifests via the #1097 validators, and
composes an extension into an in-memory PROTOCOL VIEW over a core node set — WITHOUT
executing any runtime implementation.

Graph-composition semantics (#1133):
  * Source graphs stay separate — the core graph and each extension graph are authored
    independently; no cross-package edges are ever authored.
  * Cross-package linkage uses exactly ONE relation: ``realizes`` (an extension node
    realizes a core node), declared in the extension manifest.
  * ``depends_on.targets.coach_nodes`` is DERIVED from ``realizes`` (and validated for
    consistency when both are present).
  * ``design_candidates`` may be referenced but may never be realized.
  * The composed view materializes ``realizes`` mappings as DERIVED edges in memory
    only (never written back), each carrying the provenance triple
    (core authority, extension realization, workspace execution target).
  * Expansion has two modes: ``core`` (source-only, default authority) and ``composed``
    (core + derived realization edges; opt-in for an enabled package set).
"""
from __future__ import annotations

import logging
import pathlib

import yaml

import atdd
from atdd.planner.commands.author import AuthorInputError
from atdd.planner.commands.author_manifest import (
    validate_extension_manifest,
    validate_implementation_manifest,
    validate_workspace_manifest,
)

_log = logging.getLogger(__name__)

EXTENSION_MANIFEST = "atdd.extension.yaml"
WORKSPACE_MANIFEST = "atdd.workspace.yaml"
IMPLEMENTATION_MANIFEST = "atdd.implementation.yaml"
CORE_GRAPH_ID = "atdd.convention.relationships"


class CompositionError(Exception):
    """Raised when a package cannot be composed against core (resolution/ownership)."""


# ─── discovery ──────────────────────────────────────────────────────────────
def discover_packages(root) -> list[dict]:
    """Walk ``root`` for package manifests. Returns one dict per package:
    ``{kind, dir, manifest_path, manifest}``."""
    root = pathlib.Path(root)
    found: list[dict] = []
    for name, kind in ((EXTENSION_MANIFEST, "extension"), (WORKSPACE_MANIFEST, "workspace")):
        for mp in sorted(root.rglob(name)):
            found.append({
                "kind": kind,
                "dir": mp.parent,
                "manifest_path": mp,
                "manifest": yaml.safe_load(mp.read_text()) or {},
            })
    return found


def validate_by_kind(pkg: dict) -> None:
    """Dispatch to the kind-specific manifest validator (raises on invalid)."""
    if pkg["kind"] == "extension":
        validate_extension_manifest(pkg["manifest"])
    elif pkg["kind"] == "workspace":
        validate_workspace_manifest(pkg["manifest"])
    else:
        raise ValueError(f"unknown package kind {pkg['kind']!r}")


# ─── core node authority (package-relative; works from a pip-installed toolkit) ──
def installed_core_node_ids() -> set[str]:
    """Core node ids resolved PACKAGE-RELATIVELY from the installed ``atdd`` package
    (``Path(atdd.__file__).parent``), per coach.source-layout — so a consumer repo can
    validate a package against core without a core checkout."""
    base = pathlib.Path(atdd.__file__).resolve().parent
    ids: set[str] = set()
    for sub in ("coach/conventions/nodes", "planner/conventions/nodes"):
        d = base / sub
        if d.exists():
            for f in d.glob("*.convention.yaml"):
                rid = (yaml.safe_load(f.read_text()) or {}).get("rule_id")
                if rid:
                    ids.add(rid)
    return ids


# ─── extension manifest accessors ───────────────────────────────────────────
def extension_owned_node_ids(ext_pkg: dict) -> set[str]:
    ids: set[str] = set()
    for rel in ((ext_pkg["manifest"].get("owns") or {}).get("conventions") or []):
        p = ext_pkg["dir"] / rel
        if p.exists():
            rid = (yaml.safe_load(p.read_text()) or {}).get("rule_id")
            if rid:
                ids.add(rid)
    return ids


def extension_target_nodes(ext_manifest: dict) -> list[str]:
    return list(((ext_manifest.get("depends_on") or {}).get("targets") or {}).get("coach_nodes") or [])


def extension_design_candidates(ext_manifest: dict) -> list[str]:
    return list(((ext_manifest.get("depends_on") or {}).get("design_candidates") or {}).get("coach_nodes") or [])


def realizes_mappings(ext_manifest: dict) -> list[tuple]:
    return [(m.get("extension_node"), m.get("core_node"))
            for m in (ext_manifest.get("realizes") or []) if isinstance(m, dict)]


def declared_workspace_id(ext_manifest: dict):
    ws = (ext_manifest.get("depends_on") or {}).get("workspaces") or []
    return ws[0].get("id") if ws and isinstance(ws[0], dict) else None


def extension_graph_edges(ext_pkg: dict) -> list[dict]:
    gp = ext_pkg["dir"] / "relationships.yaml"
    if not gp.exists():
        return []
    return (yaml.safe_load(gp.read_text()) or {}).get("edges") or []


# Edge-endpoint keys across both edge schemas: core (source_ref/target_ref) and
# the extension-local shorthand (from/to).
_EDGE_ENDPOINT_KEYS = ("source_ref", "target_ref", "from", "to")


def extension_orphan_nodes(ext_pkg: dict) -> set[str]:
    """Extension-owned convention nodes referenced by no internal relationship edge.

    Extends the core ``planner.relationship.no-orphan-nodes`` rule to extension
    packages: every convention node an extension owns must be an endpoint of at
    least one edge in the extension's own relationships.yaml. A node referenced by
    no edge is an orphan in the extension's local graph.
    """
    # Exclude the demo.* sample namespace, mirroring the core
    # planner.relationship.no-orphan-nodes rule (sample nodes are not real nodes).
    owned = {rid for rid in extension_owned_node_ids(ext_pkg) if not rid.startswith("demo.")}
    referenced: set[str] = set()
    for edge in extension_graph_edges(ext_pkg):
        for key in _EDGE_ENDPOINT_KEYS:
            val = edge.get(key)
            if val:
                referenced.add(str(val).split("#", 1)[0])
    return owned - referenced


# ─── the realization gate ───────────────────────────────────────────────────
def validate_realizes(ext_pkg: dict, core_ids: set[str]) -> set[str]:
    """Validate the extension's ``realizes`` block + cross-graph cleanliness. Raises
    CompositionError on any violation. Returns the set of realized core node ids."""
    ext = ext_pkg["manifest"]
    owned = extension_owned_node_ids(ext_pkg)
    own_candidates = set(extension_design_candidates(ext))
    errors: list[str] = []
    realized_core: set[str] = set()

    for en, cn in realizes_mappings(ext):
        if not en or not cn:
            errors.append(f"realizes entry must declare both extension_node and core_node: {(en, cn)!r}")
            continue
        if en not in owned:
            errors.append(f"realizes.extension_node {en!r} is not owned by this extension")
        if cn in own_candidates:
            errors.append(f"realizes.core_node {cn!r} is a design_candidate and cannot be realized")
        elif cn not in core_ids:
            errors.append(f"realizes.core_node {cn!r} does not resolve to a shipped core node")
        else:
            realized_core.add(cn)

    # depends_on.targets must be DERIVED from realizes (no duplication/drift) when
    # realizes is present.
    if ext.get("realizes"):
        declared = set(extension_target_nodes(ext))
        extra = declared - realized_core
        if extra:
            errors.append(f"depends_on.targets not derived from realizes (unrealized targets: {sorted(extra)})")

    # no AUTHORED cross-package edges: an extension graph edge must not reference a core node
    for e in extension_graph_edges(ext_pkg):
        for ref in (e.get("source_ref"), e.get("target_ref")):
            base = str(ref or "").split("#", 1)[0]
            if base in core_ids:
                errors.append(f"authored cross-package edge references core node {base!r}; "
                              "cross-package linkage must use realizes, not graph edges")

    if errors:
        raise CompositionError("; ".join(errors))
    return realized_core


# ─── the forcing rule: a transport provider MUST realize the mediation obligation ──
# The core obligation a decision-mediation / agent-session-transport provider must
# realize so dispatch can verify the channel is live before spawning a worker (#1268).
MEDIATION_OBLIGATION_NODE = "coach.execution.dispatch-verifies-channel-live"
# Capability domains that move/orchestrate the decision-mediation channel. A provider
# in either domain carries the live-channel obligation.
_TRANSPORT_MEDIATION_DOMAINS = frozenset({"transport", "orchestration"})


def declares_transport_mediation_capability(manifest: dict) -> bool:
    """True if the package declares a decision-mediation / agent-session-transport
    capability — any capability in the ``transport`` or ``orchestration`` domain."""
    for cap in (manifest.get("capabilities") or []):
        if isinstance(cap, dict) and cap.get("domain") in _TRANSPORT_MEDIATION_DOMAINS:
            return True
    return False


def validate_transport_realizes_mediation(pkg: dict, core_ids: set[str]) -> None:
    """Forcing rule ``coach.substrate.transport-realizes-mediation`` (#1268 part B).

    A package that declares the decision-mediation / agent-session-transport
    (``transport`` or ``orchestration``) capability MUST declare a ``realizes`` edge
    whose ``core_node`` is the ``dispatch-verifies-channel-live`` obligation. A
    transport provider that does not realize the obligation could spawn a worker
    against a dead mediation channel whose gated decisions never surface, so admission
    REFUSES it (raises ``CompositionError``).

    Distinct from ``validate_realizes`` (which checks a realizes block is well-formed):
    this is the FORCING check — it demands the obligation be realized at all. It runs
    for any package kind, since capabilities are declared by workspace providers."""
    manifest = pkg["manifest"]
    if not declares_transport_mediation_capability(manifest):
        return
    if MEDIATION_OBLIGATION_NODE not in core_ids:
        raise CompositionError(
            f"core obligation {MEDIATION_OBLIGATION_NODE!r} is not a shipped core node; "
            "cannot enforce coach.substrate.transport-realizes-mediation"
        )
    realized = {cn for _en, cn in realizes_mappings(manifest)}
    if MEDIATION_OBLIGATION_NODE not in realized:
        raise CompositionError(
            "package declares a decision-mediation/agent-session-transport capability "
            f"but does not realizes the {MEDIATION_OBLIGATION_NODE!r} obligation; "
            "a transport provider must prove the mediation channel is verified live "
            "before a worker is spawned, so admission refuses it "
            "(coach.substrate.transport-realizes-mediation)"
        )


# ─── the composed protocol view ─────────────────────────────────────────────
def compose_protocol_view(core_node_ids, ext_pkg: dict, *, mode: str = "composed") -> dict:
    """Compose an extension into a protocol VIEW over the core node set. Pure data —
    no implementation is executed. ``mode='core'`` is source-only (no derived edges);
    ``mode='composed'`` materializes ``realizes`` mappings as derived edges carrying the
    provenance triple. Derived edges live ONLY in the returned view, never written back."""
    if mode not in ("core", "composed"):
        raise ValueError(f"unknown expansion mode {mode!r}")
    ext = ext_pkg["manifest"]
    core = set(core_node_ids)
    contributed = sorted(extension_owned_node_ids(ext_pkg))
    targets = extension_target_nodes(ext)
    candidates = extension_design_candidates(ext)
    ws_id = declared_workspace_id(ext)

    derived_edges: list[dict] = []
    realization_index: dict[str, list] = {}
    if mode == "composed":
        for en, cn in realizes_mappings(ext):
            if cn in core:
                derived_edges.append({
                    "relation": "realizes",
                    "source_ref": en,                 # extension node
                    "target_ref": cn,                 # core node
                    "derived": True,                  # composed artifact, NOT authored source
                    "provenance": {
                        "core_authority": cn,
                        "extension_realization": en,
                        "execution_target": ws_id,
                    },
                })
                realization_index.setdefault(cn, []).append(en)

    return {
        "extension_id": ext.get("extension_id"),
        "mode": mode,
        "core_node_count": len(core),
        "contributes": contributed,
        "targets_resolved": [t for t in targets if t in core],
        "targets_unresolved": [t for t in targets if t not in core],
        "design_candidates": candidates,          # non-normative references, never realized
        "derived_edges": derived_edges,            # composed mode only
        "realization_index": realization_index,    # core_node -> [extension nodes]
        "executed_implementations": [],            # composition NEVER runs the runtime
    }


# ─── package validation orchestrator + CLI bridge ───────────────────────────
def validate_package(path, *, core_ids: "set[str] | None" = None) -> dict:
    """Validate a single package directory against core. Raises CompositionError /
    AuthorInputError / jsonschema.ValidationError on any violation. Returns a report."""
    import json

    import jsonschema

    root = pathlib.Path(path)
    pkgs = discover_packages(root)
    if not pkgs:
        raise CompositionError(f"no package manifest (atdd.extension.yaml / atdd.workspace.yaml) under {root}")
    if core_ids is None:
        core_ids = installed_core_node_ids()
    schema_path = (pathlib.Path(atdd.__file__).resolve().parent
                   / "planner" / "schemas" / "author" / "convention-node.schema.json")
    node_schema = json.loads(schema_path.read_text())

    report = {"root": str(root), "packages": [], "views": []}
    for p in pkgs:
        validate_by_kind(p)
        # Forcing rule (#1268): a transport/mediation provider must realize the
        # dispatch-verifies-channel-live obligation. Runs for every kind.
        validate_transport_realizes_mediation(p, core_ids)
        entry = {"kind": p["kind"]}
        # Enforce the validator/family contract on every shipped implementation
        # manifest in the package (atdd.core.implementation-schema).
        impl_count = 0
        for imp in sorted(p["dir"].rglob(IMPLEMENTATION_MANIFEST)):
            try:
                validate_implementation_manifest(yaml.safe_load(imp.read_text()) or {})
            except AuthorInputError as exc:
                raise CompositionError(
                    f"invalid implementation manifest {imp.relative_to(root)}: {exc}") from exc
            impl_count += 1
        entry["implementations"] = impl_count
        if p["kind"] == "extension":
            entry["id"] = p["manifest"].get("extension_id")
            for rel in ((p["manifest"].get("owns") or {}).get("conventions") or []):
                node_path = p["dir"] / rel
                if not node_path.exists():
                    raise CompositionError(f"owns path missing: {rel}")
                jsonschema.validate(yaml.safe_load(node_path.read_text()), node_schema)
            validate_realizes(p, core_ids)
            orphans = extension_orphan_nodes(p)
            if orphans:
                raise CompositionError(
                    "orphan convention node(s) referenced by no relationship edge: "
                    + ", ".join(sorted(orphans))
                )
            view = compose_protocol_view(core_ids, p, mode="composed")
            if view["executed_implementations"]:
                raise CompositionError("composition must not execute runtime implementations")
            report["views"].append(view)
        else:
            entry["id"] = p["manifest"].get("workspace_id")
        report["packages"].append(entry)
    return report


def validate_package_cli(path) -> int:
    """`atdd validate package <path>` — validate + compose a package against installed
    core, with no runtime execution. Returns a process exit code."""
    if not path:
        print("Error: 'atdd validate package <path>' requires a package directory")
        return 2
    try:
        report = validate_package(path)
    except Exception as exc:  # top-level CLI boundary: log + surface + non-zero exit (not swallowed)
        _log.warning("package validation failed", extra={"path": str(path), "error": str(exc)})
        print(f"✗ package validation failed: {exc}")
        return 1
    print(f"✓ {report['root']}: {len(report['packages'])} package(s) valid against core")
    for v in report["views"]:
        print(f"  {v['extension_id']}: realizes {len(v['derived_edges'])} core node(s) "
              f"[{', '.join(sorted(v['realization_index'])) or 'targets-only'}]; "
              f"runtime executed: {len(v['executed_implementations'])}")
    return 0
