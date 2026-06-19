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

    GREEN target: recompute installer.compute_digest(project_root / installed_path)
    and raise DigestMismatchError if it != entry['digest'] (the tamper boundary).
    Never imports an implementation module.
    """
    raise NotImplementedError("C001: re-verify installed-package digest before loading (GREEN)")


def load_enabled_packages(project_root: str | Path) -> list[LoadedPackage]:
    """Load every ``enabled`` lock artifact from its installed_path, digest-verified.

    GREEN target: read_lock -> filter enabled -> verify_package_digest (refuse on
    mismatch) -> inspect_package (manifest only) -> index implementations by
    realizes_convention. A disabled or lock-absent package is never loaded.
    """
    raise NotImplementedError("L001: load enabled packages from the lock (GREEN)")
