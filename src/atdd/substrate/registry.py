"""Registry index reader + search (WMBT L001).

A registry index is a catalog of admittable artifacts (canonical id + aliases +
tags + versions). `atdd search` locates candidates by alias, canonical id, tags,
and (optionally) kind. Search LOCATES — it never installs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from atdd.substrate import schemas


@dataclass(frozen=True)
class RegistryEntry:
    """One catalog entry. Aliases are UX; ``id`` is authoritative for lockfiles."""

    id: str
    kind: str
    latest_version: str
    aliases: tuple = ()
    tags: tuple = ()
    display_name: str = ""
    summary: str = ""
    trust: str = ""
    source: str = ""
    versions: tuple = ()

    @classmethod
    def from_dict(cls, d: dict) -> "RegistryEntry":
        return cls(
            id=d["id"],
            kind=d["kind"],
            latest_version=d["latest_version"],
            aliases=tuple(d.get("aliases", [])),
            tags=tuple(d.get("tags", [])),
            display_name=d.get("display_name", ""),
            summary=d.get("summary", ""),
            trust=d.get("trust", ""),
            source=d.get("source", ""),
            versions=tuple(d.get("versions", [])),
        )


def load_registry_index(path: str | Path) -> list[RegistryEntry]:
    """Load + schema-validate a registry index file, returning its entries."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    schemas.validate_registry_index(data, source=path)
    return [RegistryEntry.from_dict(e) for e in data.get("entries", [])]


def search(
    entries: list[RegistryEntry], query: str, *, kind: str | None = None
) -> list[RegistryEntry]:
    """Locate entries matching ``query`` by alias (exact), id (substring), or tag.

    ``kind`` (``extension``/``workspace``) restricts results. Returns matches in
    registry order; a non-matching query returns an empty list (and installs nothing).
    """
    q = (query or "").strip().lower()
    out: list[RegistryEntry] = []
    for e in entries:
        if kind is not None and e.kind != kind:
            continue
        aliases = {a.lower() for a in e.aliases}
        tags = {t.lower() for t in e.tags}
        if q in e.id.lower() or q in aliases or q in tags:
            out.append(e)
    return out
