"""Load enabled packages from the substrate lock + digest re-verify (WMBT L001, C001).

Binding loads only what the lock says is live: it reads ``.atdd/substrate.lock.yaml``,
takes each artifact whose ``enabled`` is true, and loads it from its recorded
``installed_path`` — but BEFORE loading a package it re-computes the package's
sha256 digest and compares it to the ``digest`` recorded in the lock. If the
installed files were mutated since admission (digest mismatch) the package is
refused and never loaded, because bind is the first layer that runs admitted code
and admit's validation only proves what was admitted, not what is on disk now.

A ``LoadedPackage`` carries the manifest (read without executing any code) and the
implementations it ships, indexed by ``realizes_convention`` downstream.

GREEN targets:
- ``verify_package_digest`` re-computes ``installer.compute_digest(installed_path)``
  and raises ``DigestMismatchError`` when it differs from the lock entry's digest.
- ``load_enabled_packages`` filters to ``enabled`` artifacts, verifies each digest,
  and loads the manifest via ``admission.inspect_package`` (no implementation import).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class LoadedPackage:
    """An enabled, digest-verified package loaded from the lock (no code executed)."""

    id: str
    kind: str
    version: str
    installed_path: Path
    manifest: dict = field(default_factory=dict)
    implementations: list = field(default_factory=list)


def verify_package_digest(project_root: str | Path, entry: dict) -> None:
    """Re-verify a lock entry's installed package against its recorded digest.

    Recomputes the sha256 digest of the installed package directory and raises
    ``DigestMismatchError`` when it differs from the lock entry's ``digest`` — the
    tamper boundary, run BEFORE any package load. Never imports an implementation
    module (digest is computed over file bytes only).
    """
    from atdd.substrate import installer
    from atdd.substrate.binding import DigestMismatchError

    pkg_id = entry.get("id", "<unknown>")
    expected = entry.get("digest")
    if not expected:
        raise DigestMismatchError(f"{pkg_id}: lock entry has no digest to verify against")

    pkg_dir = Path(project_root) / entry["installed_path"]
    if not pkg_dir.exists():
        raise DigestMismatchError(
            f"{pkg_id}: installed_path {entry['installed_path']!r} is missing on disk"
        )

    actual = installer.compute_digest(pkg_dir)
    if actual != expected:
        raise DigestMismatchError(
            f"{pkg_id}: installed package was modified since admission "
            f"(lock digest {expected}, on-disk {actual}) — refusing to load"
        )


#: The per-implementation manifest filename. Public because it is the one
#: name every reader of the vendored substrate must agree on — the
#: reverse-coherence proof resolver (#1773) walks the same files this does.
IMPLEMENTATION_MANIFEST = "atdd.implementation.yaml"


def _discover_implementations(pkg_dir: Path) -> list[dict]:
    """Read the implementation manifests a package ships, without executing code.

    Returns the manifest dicts (implementation_id, targets_workspace,
    contract_version, realizes_convention, entrypoint) for every
    ``**/atdd.implementation.yaml`` under the package — YAML only, never an
    implementation module.
    """
    import yaml

    impls: list[dict] = []
    for mp in sorted(pkg_dir.rglob(IMPLEMENTATION_MANIFEST)):
        try:
            data = yaml.safe_load(mp.read_text(encoding="utf-8")) or {}
        except (OSError, ValueError):
            continue
        if data.get("kind") != "implementation":
            continue
        # A manifest binds rules either by OWNERSHIP (realizes_convention) or, for a
        # family detector authored against the v1.1 schema, by emits_rule_ids alone.
        # Requiring realizes_convention silently dropped the latter.
        if data.get("implementation_id") and (
            data.get("realizes_convention") or data.get("emits_rule_ids")
        ):
            data["_manifest_path"] = str(mp)
            impls.append(data)
    return impls


def load_enabled_packages(project_root: str | Path) -> list[LoadedPackage]:
    """Load every ``enabled`` lock artifact from its installed_path, digest-verified.

    read_lock -> filter ``enabled`` -> verify_package_digest (refuses a tampered
    package, fail-closed) -> inspect_package (manifest only) -> discover the
    implementations it ships. A disabled or lock-absent package is never loaded,
    and no implementation module is imported.
    """
    from atdd.substrate import admission, installer

    root = Path(project_root)
    loaded: list[LoadedPackage] = []
    for entry in installer.list_substrate(root):
        if not entry.get("enabled", False):
            continue
        verify_package_digest(root, entry)  # tamper boundary (raises on mismatch)
        pkg_dir = root / entry["installed_path"]
        pkg = admission.inspect_package(pkg_dir)
        loaded.append(
            LoadedPackage(
                id=entry["id"],
                kind=entry["kind"],
                version=entry["version"],
                installed_path=pkg_dir,
                manifest=pkg["manifest"],
                implementations=_discover_implementations(pkg_dir),
            )
        )
    return loaded
