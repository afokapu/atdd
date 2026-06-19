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


def load_enabled_packages(project_root: str | Path) -> list[LoadedPackage]:
    """Load every ``enabled`` lock artifact from its installed_path, digest-verified.

    GREEN target: read_lock -> filter enabled -> verify_package_digest (refuse on
    mismatch) -> inspect_package (manifest only) -> index implementations by
    realizes_convention. A disabled or lock-absent package is never loaded.
    """
    raise NotImplementedError("L001: load enabled packages from the lock (GREEN)")
