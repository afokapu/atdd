# Component: component:author-atdd-substrate:substrate-spine:Compose:backend:application
"""Package discovery + protocol-view composition (#1130).

The consumption counterpart to the ``author_*`` substrate. Discovers installed
extension/workspace packages, validates their manifests via the #1097 validators, and
composes an extension into an in-memory PROTOCOL VIEW over a core node set — WITHOUT
executing any runtime implementation. Loading/validating/composing only; the runtime
(running validators/shims/workspaces) is deliberately out of scope.
"""
from __future__ import annotations

import pathlib

import yaml

from atdd.planner.commands.author_manifest import (
    validate_extension_manifest,
    validate_workspace_manifest,
)

EXTENSION_MANIFEST = "atdd.extension.yaml"
WORKSPACE_MANIFEST = "atdd.workspace.yaml"


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


def extension_target_nodes(ext_manifest: dict) -> list[str]:
    return list(((ext_manifest.get("depends_on") or {}).get("targets") or {}).get("coach_nodes") or [])


def extension_design_candidates(ext_manifest: dict) -> list[str]:
    return list(((ext_manifest.get("depends_on") or {}).get("design_candidates") or {}).get("coach_nodes") or [])


def compose_protocol_view(core_node_ids, ext_pkg: dict) -> dict:
    """Compose an extension into a protocol VIEW over the core node set. Pure data —
    no implementation is executed. ``targets_unresolved`` MUST be empty for a valid
    composition; ``design_candidates`` are carried as non-normative references."""
    ext = ext_pkg["manifest"]
    core = set(core_node_ids)
    targets = extension_target_nodes(ext)
    candidates = extension_design_candidates(ext)
    contributed: list[str] = []
    for rel in ((ext.get("owns") or {}).get("conventions") or []):
        p = ext_pkg["dir"] / rel
        if p.exists():
            rid = (yaml.safe_load(p.read_text()) or {}).get("rule_id")
            if rid:
                contributed.append(rid)
    return {
        "extension_id": ext.get("extension_id"),
        "core_node_count": len(core),
        "contributes": contributed,
        "targets_resolved": [t for t in targets if t in core],
        "targets_unresolved": [t for t in targets if t not in core],
        "design_candidates": candidates,        # non-normative references, never dependencies
        "executed_implementations": [],          # composition NEVER runs the runtime
    }
