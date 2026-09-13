# Component: component:atdd-plan-core:migration:RegistryProjection:backend:domain
"""Projection of ``plan/_trains.yaml`` for the train-URN migration (#1421, #1986).

Split out of ``train_urn_migration`` (#1986), which had grown past the 500-line
report threshold that ``coder.refactor.quality-file-length`` ratchets. The seam
is a real responsibility boundary, not an arbitrary cut: this module owns READING
and WRITING the bucketed registry document, while ``train_urn_migration`` owns the
alias map and the relocation of train FILES. Nothing here touches a train document.

The registry is a two-level bucketed document ``trains: {group: {section:
[entries]}}``. Every reader (coach ``_flatten_nested_trains``, the planner
``trains_registry`` fixture, ``issue_graph``, ``inventory``) iterates that nesting
generically and keys off each ENTRY's fields (``train_id``, ``path``, ``wagons``),
never off the bucket key names — so the migration is free to re-key the buckets by
``subject``/``category`` without breaking a reader.

The alias facts live in ``train_urn_migration`` and are imported lazily inside the
functions that need them: this module is the consumer of that data, and a
module-level import would make the pair circular.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

_TRAINS_DIR_REL = Path("plan") / "_trains"
_REGISTRY_REL = Path("plan") / "_trains.yaml"


# ---------------------------------------------------------------------------
# Registry (plan/_trains.yaml) helpers
#
# The registry is a two-level bucketed document ``trains: {group: {section:
# [entries]}}``. Every reader (coach ``_flatten_nested_trains``, the planner
# ``trains_registry`` fixture, ``issue_graph``, ``inventory``) iterates that
# nesting generically and keys off each ENTRY's fields (``train_id``, ``path``,
# ``wagons``), never off the bucket key names — so the migration is free to
# re-key the buckets by ``subject``/``category`` without breaking a reader.
# ---------------------------------------------------------------------------
def _collect_train_entries(entries, flat: Dict[str, dict]) -> None:
    """Key every well-formed entry of a train list into ``flat`` by its train_id.
    A non-list (malformed section) contributes nothing."""
    if not isinstance(entries, list):
        return
    for entry in entries:
        if isinstance(entry, dict) and entry.get("train_id"):
            flat[entry["train_id"]] = entry


def _flatten_registry(trains_data) -> Dict[str, dict]:
    """Flatten a ``trains:`` document into ``{train_id: entry}``.

    Mirrors coach ``registry._flatten_nested_trains``: tolerates the nested
    ``{group: {section: [entries]}}`` shape and a legacy flat list.
    """
    flat: Dict[str, dict] = {}
    if isinstance(trains_data, dict):
        for _group, sections in trains_data.items():
            if not isinstance(sections, dict):
                continue
            for _section, entries in sections.items():
                _collect_train_entries(entries, flat)
    elif isinstance(trains_data, list):
        _collect_train_entries(trains_data, flat)
    return flat


def _load_registry(root: Path) -> Dict[str, dict]:
    """Return ``{train_id: entry}`` for the on-disk ``plan/_trains.yaml``."""
    registry_path = Path(root) / _REGISTRY_REL
    if not registry_path.exists():
        return {}
    raw = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    return _flatten_registry(raw.get("trains", {}) if isinstance(raw, dict) else {})


def _write_registry(root: Path, doc: dict) -> Path:
    registry_path = Path(root) / _REGISTRY_REL
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        yaml.safe_dump(doc, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    return registry_path


def _registry_entry(existing: Dict[str, dict], legacy_id: str) -> dict:
    """The pre-migration registry entry for ``legacy_id`` — matched by the legacy
    id or (on an idempotent re-run) by its already-typed id. ``{}`` if absent."""
    from .train_urn_migration import (  # local: avoids a circular import
        LEGACY_TRAIN_ALIASES, forward, category_for_legacy,
    )
    typed = forward(legacy_id)
    return existing.get(legacy_id) or existing.get(typed) or {}


#: Bucket that holds any preserved registry row whose subject cannot be derived
#: (a legacy id with no alias). Readers key off each ENTRY, never the bucket
#: name, so the row stays fully readable — the odd bucket is a visible marker
#: that a train is still unmigrated, not a functional distinction.
_UNMIGRATED_BUCKET = "_unmigrated"


def subject_of_typed(train_id: str) -> Optional[str]:
    """The ``<subject>`` token of a typed ``train:<subject>:<slug>`` id, else None."""
    parts = train_id.split(":")
    if len(parts) == 3 and parts[0] == "train" and all(parts[1:]):
        return parts[1]
    return None


def _owned_ids() -> set:
    """Every registry id this migration authors: each aliased legacy id and the
    typed URN it becomes. Anything else in the registry belongs to someone else."""
    from .train_urn_migration import (  # local: avoids a circular import
        LEGACY_TRAIN_ALIASES, forward, category_for_legacy,
    )
    from .train_urn_migration import build_alias_map
    return set(LEGACY_TRAIN_ALIASES) | set(build_alias_map().values())


def _carry_through_unowned(
    trains: Dict[str, Dict[str, List[dict]]], existing: Dict[str, dict]
) -> None:
    """Copy every row of *existing* this migration does not own into *trains*.

    Both projections re-derive the registry from :data:`LEGACY_TRAIN_ALIASES`, so
    without this a train that no alias names — one another issue typed — loses its
    row while its document stays on disk (#1986). Rows are copied verbatim and
    filed under their own subject, so a carried-through row is byte-identical
    across a migrate/revert round trip.
    """
    owned = _owned_ids()
    for train_id, entry in sorted(existing.items()):
        if train_id in owned:
            continue
        subject = subject_of_typed(train_id)
        if subject is None:
            subject = _UNMIGRATED_BUCKET
            logger.warning(
                "registry projection: preserving a row whose subject cannot be "
                "derived; it has no alias and is not a typed URN",
                extra={"train_id": train_id},
            )
        category = entry.get("category") or "nominal"
        trains.setdefault(subject, {}).setdefault(category, []).append(dict(entry))


def _rewrite_registry_typed(root: Path, existing: Dict[str, dict]) -> Path:
    """Project the typed ``plan/_trains.yaml``.

    Buckets are re-keyed ``trains: {<subject>: {<category>: [entries]}}``. Each
    aliased entry carries the typed ``train_id``, the ``category`` field, the
    nested ``path``, and the ``wagons``/``description`` preserved from *existing*.

    Rows in *existing* that this migration does NOT own — trains other issues
    typed, which no alias names — are carried through VERBATIM (#1986). The
    projection used to rebuild the document from :data:`LEGACY_TRAIN_ALIASES`
    alone, which silently evicted every such row while leaving its document on
    disk: precisely the half-applied state ``planner.train.registry-coherence``
    rejects. A row is owned only if it is an aliased legacy id or the typed URN
    of one; everything else survives untouched.
    """
    from .train_urn_migration import (  # local: avoids a circular import
        LEGACY_TRAIN_ALIASES, forward, category_for_legacy,
    )
    trains: Dict[str, Dict[str, List[dict]]] = {}

    for legacy_id, (subject, slug) in sorted(LEGACY_TRAIN_ALIASES.items()):
        typed = forward(legacy_id)
        category = category_for_legacy(legacy_id)
        prior = _registry_entry(existing, legacy_id)
        entry = {
            "train_id": typed,
            "category": category,
            "description": prior.get("description", ""),
            "path": f"plan/_trains/{subject}/{slug}.yaml",
            "wagons": list(prior.get("wagons", []) or []),
        }
        trains.setdefault(subject, {}).setdefault(category, []).append(entry)

    _carry_through_unowned(trains, existing)

    for subject in trains:
        for category in trains[subject]:
            trains[subject][category].sort(key=lambda e: e["train_id"])
    return _write_registry(root, {"trains": trains})


def _rewrite_registry_legacy(root: Path, existing: Dict[str, dict]) -> Path:
    """Project the legacy digit-bucketed ``plan/_trains.yaml`` (revert side).

    Rebuilds the ``{digit-theme: {digitdigit-theme-category: [entries]}}`` shape
    the pre-migration registry used, so the round-tripped file stays valid for
    every reader. Entries are matched to their legacy ids via the inverse map.
    """
    from .train_urn_migration import (  # local: avoids a circular import
        LEGACY_TRAIN_ALIASES, forward, category_for_legacy,
    )
    from .train_urn_migration import _CATEGORY_BY_DIGIT
    from atdd.coach.utils.theme_map import get_theme_map
    from atdd.coach.utils.config import load_atdd_config

    theme_map = get_theme_map(load_atdd_config(Path(root)))
    trains: Dict[str, Dict[str, List[dict]]] = {}
    for legacy_id in sorted(LEGACY_TRAIN_ALIASES):
        typed = forward(legacy_id)
        prior = existing.get(typed) or existing.get(legacy_id) or {}
        theme_digit = legacy_id[0] if legacy_id[:1].isdigit() else "0"
        category_digit = legacy_id[1] if len(legacy_id) > 1 and legacy_id[1].isdigit() else "0"
        theme_name = theme_map.get(theme_digit, "unknown")
        category_name = _CATEGORY_BY_DIGIT.get(category_digit, "nominal")
        group = f"{theme_digit}-{theme_name}"
        section = f"{theme_digit}{category_digit}-{theme_name}-{category_name}"
        entry = {
            "train_id": legacy_id,
            "description": prior.get("description", ""),
            "path": f"plan/_trains/{legacy_id}.yaml",
            "wagons": list(prior.get("wagons", []) or []),
        }
        trains.setdefault(group, {}).setdefault(section, []).append(entry)

    # Symmetric with the typed projection: a rollback that evicted rows would be
    # destructive in its own right — and, because the apply-test fixture normalizes
    # through revert, that eviction was what hid the forward defect (#1986).
    _carry_through_unowned(trains, existing)

    for group in trains:
        for section in trains[group]:
            trains[group][section].sort(key=lambda e: e["train_id"])
    return _write_registry(root, {"trains": trains})
