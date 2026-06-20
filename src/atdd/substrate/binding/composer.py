"""Compose the capability graph from loaded packages (WMBT L001).

Indexes the implementations the enabled, digest-verified packages ship by their
``realizes_convention`` — the lookup the scope-selector and binder use to decide,
for a given convention, which admitted implementation (if any) owns its gating.
Pure data: it consumes ``LoadedPackage`` records (manifests only) and never
imports or runs an implementation module.
"""
from __future__ import annotations

from atdd.substrate.binding import BindingError
from atdd.substrate.binding.lock_loader import LoadedPackage


class DuplicateConventionError(BindingError):
    """Two admitted implementations claim to realize the same convention."""


def index_by_convention(packages: list[LoadedPackage]) -> dict[str, dict]:
    """Map ``realizes_convention`` -> implementation record across loaded packages.

    Raises ``DuplicateConventionError`` if two admitted implementations realize the
    same convention (an ambiguous binding the operator must resolve). The record
    carries the implementation manifest plus the owning package id.
    """
    index: dict[str, dict] = {}
    for pkg in packages:
        for impl in pkg.implementations:
            convention = impl["realizes_convention"]
            if convention in index:
                prior = index[convention]
                raise DuplicateConventionError(
                    f"convention {convention!r} is realized by both "
                    f"{prior['implementation_id']!r} (package {prior['_package_id']}) and "
                    f"{impl['implementation_id']!r} (package {pkg.id})"
                )
            index[convention] = {**impl, "_package_id": pkg.id}
    return index
