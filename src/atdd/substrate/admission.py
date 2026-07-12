"""Substrate admission orchestration (WMBTs C001/C002/C003/E001/C004).

`admit()` is the core of `atdd add`: resolve a package, validate its manifest +
owned files + realizes/depends_on against core (reusing the package-composition
seam read-only), compose an in-memory protocol view, record a sha256 digest, and
install into a versioned `.atdd/` home — writing intent + lock.

INVARIANT (C001): admission NEVER imports or executes an extension implementation
module. It inspects manifests and composes pure data only; `executed_implementations`
is always empty. Runtime binding is a later, separate wagon.

RED: `admit` is an unimplemented stub; C001's tests fail until GREEN ships the
non-executing admission path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from atdd.planner.commands import compose
from atdd.substrate import installer

# Manifest filename → package kind. Inspecting a package reads ONLY these YAML
# manifests; it never imports an implementation module.
_MANIFESTS = (("atdd.extension.yaml", "extension"), ("atdd.workspace.yaml", "workspace"))


class AdmissionError(ValueError):
    """A package could not be admitted (manifest, realization, or dependency fault)."""


@dataclass(frozen=True)
class AdmissionResult:
    """Outcome of admitting one package, without executing any of its code."""

    package_id: str
    kind: str
    installed_path: Path | None = None
    digest: str | None = None
    composed: dict = field(default_factory=dict)
    # Always empty: admission never runs an extension implementation.
    executed_implementations: list = field(default_factory=list)


def inspect_package(package_dir: str | Path) -> dict:
    """Load a package's manifest WITHOUT importing any of its code.

    Returns the discovery dict ``{kind, dir, manifest_path, manifest}`` (the shape
    ``compose`` consumes). Only the YAML manifest is read — never an implementation
    module.
    """
    d = Path(package_dir)
    for name, kind in _MANIFESTS:
        mp = d / name
        if mp.exists():
            return {
                "kind": kind,
                "dir": d,
                "manifest_path": mp,
                "manifest": yaml.safe_load(mp.read_text(encoding="utf-8")) or {},
            }
    raise AdmissionError(f"no package manifest (atdd.extension.yaml / atdd.workspace.yaml) in {d}")


# owns categories whose entries are FILE/DIR PATHS (checked for existence). Other
# categories (e.g. `scopes`) list selector-type IDENTIFIERS, not paths.
_PATH_OWNS_CATEGORIES = frozenset(
    {"conventions", "relationships", "implementations", "schemas", "gates"}
)


def _validate_owned_files(pkg: dict) -> None:
    """Every PATH the manifest declares it ``owns`` must exist on disk.

    Only path-bearing categories are checked; identifier categories such as
    ``scopes`` (selector-type names like ``github_issue``) are not file paths.
    """
    owns = pkg["manifest"].get("owns") or {}
    pkg_dir = Path(pkg["dir"])
    for category, paths in owns.items():
        if category not in _PATH_OWNS_CATEGORIES:
            continue
        for rel in paths or []:
            if not isinstance(rel, str):
                continue
            if not (pkg_dir / rel).exists():
                raise AdmissionError(
                    f"owns.{category} declares {rel!r} but it does not exist in the package"
                )


def validate_and_compose(
    package_dir: str | Path, *, core_ids: "set[str] | None" = None
) -> AdmissionResult:
    """Validate a package and compose its protocol view — NO install, NO execution.

    Inspect manifest → validate manifest by kind → (extensions) validate realizes
    against core + compose the protocol view. Reads manifests and composes pure
    data only; it NEVER imports an implementation module, so
    ``executed_implementations`` is always empty. Raises ``AuthorInputError`` /
    ``AdmissionError`` on any validation failure.
    """
    pkg = inspect_package(package_dir)
    compose.validate_by_kind(pkg)  # manifest shape; raises on invalid
    _validate_owned_files(pkg)     # files the manifest claims to own must exist

    if core_ids is None:
        core_ids = compose.installed_core_node_ids()

    # Forcing rule (#1268): any package declaring the decision-mediation /
    # agent-session-transport capability MUST realize the dispatch-verifies-channel-live
    # obligation; admission refuses it otherwise. Runs for every kind (capabilities are
    # a workspace-provider concern), before the extension-only realizes/compose step.
    compose.validate_transport_realizes_mediation(pkg, core_ids)

    composed: dict = {}
    if pkg["kind"] == "extension":
        compose.validate_realizes(pkg, core_ids)  # raises on bad realization
        composed = compose.compose_protocol_view(core_ids, pkg, mode="composed")

    manifest = pkg["manifest"]
    package_id = manifest.get("extension_id") or manifest.get("workspace_id") or ""
    # Admission never runs an implementation; surface that invariant explicitly.
    executed = list(composed.get("executed_implementations", []))
    return AdmissionResult(
        package_id=package_id,
        kind=pkg["kind"],
        composed=composed,
        executed_implementations=executed,
    )


def admit(
    package_dir: str | Path,
    *,
    project_root: str | Path,
    core_ids: "set[str] | None" = None,
) -> AdmissionResult:
    """Validate + compose + install a package without executing its code. (GREEN)

    Resolve → validate manifest + owned files → validate realizes/depends_on →
    compose protocol view → sha256 digest → install into `.atdd/{kind}s/<id>/<version>/`
    → write substrate intent + lock. Refuses (raises) on any validation failure,
    leaving the substrate unchanged. Never imports an implementation module.
    """
    # Validate + compose first (raises on any fault) — leaves substrate untouched.
    composed = validate_and_compose(package_dir, core_ids=core_ids)
    pkg = inspect_package(package_dir)
    manifest = pkg["manifest"]
    version = str(manifest.get("version") or "0.0.0")

    digest = installer.compute_digest(package_dir)
    dest = installer.install(
        package_dir,
        project_root,
        kind=pkg["kind"],
        package_id=composed.package_id,
        version=version,
    )
    entry = {
        "id": composed.package_id,
        "kind": pkg["kind"],
        "version": version,
        "digest": digest,
        "installed_path": str(Path(dest).relative_to(Path(project_root))),
        "enabled": True,
    }
    deps = [{"id": w["id"]} for w in (manifest.get("depends_on", {}).get("workspaces", []) or []) if w.get("id")]
    if deps:
        entry["workspaces"] = deps
    installer.upsert_lock_entry(project_root, entry)

    return AdmissionResult(
        package_id=composed.package_id,
        kind=pkg["kind"],
        installed_path=dest,
        digest=digest,
        composed=composed.composed,
        executed_implementations=[],
    )


def remove(
    ref: str, *, project_root: str | Path, force: bool = False, prune: bool = False
) -> dict:
    """Withdraw an artifact from the lock, refusing if others depend on it.

    Refuses (raises ``AdmissionError``) when another admitted artifact depends on
    the target, unless ``force``. With ``prune``, also removes the target's
    workspaces when no remaining artifact depends on them. Returns
    ``{removed, pruned}``.
    """
    arts = installer.list_substrate(project_root)
    target = next((a for a in arts if a.get("id") == ref), None)
    if target is None:
        raise AdmissionError(f"{ref!r} is not in the installed substrate")

    dependents = [
        a["id"]
        for a in arts
        if a.get("id") != target["id"]
        and any(w.get("id") == target["id"] for w in (a.get("workspaces") or []))
    ]
    if dependents and not force:
        raise AdmissionError(
            f"{target['id']} is depended on by {', '.join(dependents)}; pass --force to remove anyway"
        )

    installer.remove_lock_entry(project_root, target["id"])
    pruned: list[str] = []
    if prune:
        remaining = installer.list_substrate(project_root)
        for w in target.get("workspaces") or []:
            wid = w.get("id")
            still_needed = any(
                any(dep.get("id") == wid for dep in (a.get("workspaces") or []))
                for a in remaining
            )
            if not still_needed and any(a.get("id") == wid for a in remaining):
                installer.remove_lock_entry(project_root, wid)
                pruned.append(wid)
    return {"removed": target["id"], "pruned": pruned}
