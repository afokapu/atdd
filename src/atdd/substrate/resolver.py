"""Artifact reference resolution (WMBT C002).

Resolve a user-supplied ref to exactly one catalog entry. A canonical id is
authoritative and accepted directly. An alias is a UX convenience: it must
resolve to exactly one entry — if two or more entries share the alias, resolution
is REFUSED with the candidate ids so the operator re-runs with an unambiguous id.
"""
from __future__ import annotations

from atdd.substrate.registry import RegistryEntry


class ResolutionError(ValueError):
    """A ref could not be resolved to exactly one artifact."""


class AmbiguousAliasError(ResolutionError):
    """An alias matched more than one artifact; resolution is refused."""

    def __init__(self, alias: str, candidates: list[str]) -> None:
        self.alias = alias
        self.candidates = list(candidates)
        super().__init__(
            f"alias {alias!r} is ambiguous; candidates: {', '.join(self.candidates)}. "
            "Re-run with a canonical id."
        )


def resolve(ref: str, entries: list[RegistryEntry]) -> RegistryEntry:
    """Resolve ``ref`` (canonical id or alias) to exactly one entry.

    Canonical id match wins outright. Otherwise the ref is an alias: 0 matches →
    ``ResolutionError`` (not found); 1 → that entry; ≥2 → ``AmbiguousAliasError``.
    """
    by_id = [e for e in entries if e.id == ref]
    if by_id:
        return by_id[0]
    by_alias = [e for e in entries if ref in e.aliases]
    if len(by_alias) == 1:
        return by_alias[0]
    if len(by_alias) > 1:
        raise AmbiguousAliasError(ref, [e.id for e in by_alias])
    raise ResolutionError(f"no artifact matches {ref!r}")
