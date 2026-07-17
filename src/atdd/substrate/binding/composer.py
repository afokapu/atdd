"""Compose the capability graph from loaded packages (WMBT L001).

Indexes the implementations the enabled, digest-verified packages ship by their
``realizes_convention`` — the lookup the scope-selector and binder use to decide,
for a given convention, which admitted implementation (if any) owns its gating.
Pure data: it consumes ``LoadedPackage`` records (manifests only) and never
imports or runs an implementation module.

``realizes_convention`` may name ONE convention or a LIST of them: a family
detector realizes N conventions from a single run (e.g. the train-interlocking
infrastructure detector owns five ``coder.train.interlocking-*`` rules). Each
named convention is indexed to that one implementation.

``realizes_convention`` is OWNERSHIP; ``emits_rule_ids`` is CO-EMISSION and is
deliberately NOT indexed here. A detector may emit a rule_id it does not own —
``coder.logging.structured`` emits ``coder.logging.print`` alongside its own rule,
while ``coder.logging.print`` is owned by the dedicated print detector. Indexing
by ``emits_rule_ids`` would make those two collide.
"""
from __future__ import annotations

from atdd.substrate.binding import BindingError
from atdd.substrate.binding.lock_loader import LoadedPackage


class DuplicateConventionError(BindingError):
    """Two admitted implementations claim to realize the same convention."""


def realized_conventions(implementation: dict) -> list[str]:
    """The conventions an implementation OWNS, as a list (scalar or list manifest)."""
    realizes = implementation.get("realizes_convention")
    if realizes is None:
        return []
    if isinstance(realizes, str):
        return [realizes]
    return [str(c) for c in realizes]


def index_by_convention(packages: list[LoadedPackage]) -> dict[str, dict]:
    """Map each realized convention -> implementation record across loaded packages.

    One implementation fans out across every convention it realizes. Raises
    ``DuplicateConventionError`` if two admitted implementations realize the same
    convention (an ambiguous binding the operator must resolve). The record carries
    the implementation manifest plus the owning package id.
    """
    index: dict[str, dict] = {}
    for pkg in packages:
        for impl in pkg.implementations:
            for convention in realized_conventions(impl):
                if convention in index:
                    prior = index[convention]
                    raise DuplicateConventionError(
                        f"convention {convention!r} is realized by both "
                        f"{prior['implementation_id']!r} (package {prior['_package_id']}) and "
                        f"{impl['implementation_id']!r} (package {pkg.id})"
                    )
                index[convention] = {**impl, "_package_id": pkg.id}
    return index
