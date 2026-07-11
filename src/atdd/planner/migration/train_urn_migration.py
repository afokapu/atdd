# Component: component:atdd-plan-core:migration:TrainUrnMigration:backend:domain
"""Train-URN migration tool: legacy ``NNNN-slug`` -> typed ``train:<subject>:<slug>`` (#1421).

The legacy grammar baked ``category`` into the digit prefix, so a train's
subject/slug split is a *semantic* decision that cannot be mechanized — it is
HAND-AUTHORED in :data:`LEGACY_TRAIN_ALIASES`. This module is the single source
of that map and its lossless inverse (rollback), plus the (run-last) relocation
planner. It reuses the C1 engine (``URNGrammar.train``) to build typed URNs, so
there is no second grammar here to drift from.

Two consumers share this data:
  * C2's ``TrainResolver`` reads the projected data file
    ``plan/_trains/_aliases.yaml`` (see :func:`write_alias_file`) for legacy
    dual-resolution during the migration window;
  * the destructive migration (:func:`plan_relocations` / :func:`migrate`)
    relocates ``plan/_trains/NNNN-slug.yaml`` -> ``plan/_trains/<subject>/<slug>.yaml``.

Discipline: pure data + pure functions. Nothing here mutates the repo unless a
caller explicitly invokes :func:`migrate` (run LAST, after C2 resolver + C3
schema land).
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

from atdd.coach.utils.graph.urn import URNGrammar

# ---------------------------------------------------------------------------
# Hand-authored forward map: legacy train id -> (subject, slug).
#
# subject = the durable NOUN the journey is about (registered in
# plan/_subjects.yaml); slug = the flow within that subject. ``category`` (the
# old second digit) becomes a FIELD on the migrated train, never the identity.
# ---------------------------------------------------------------------------
LEGACY_TRAIN_ALIASES: Dict[str, Tuple[str, str]] = {
    # 0-commons / nominal — ATDD validating its own lifecycle.
    "0001-self-compliance-validate": ("self-compliance", "validate-lifecycle"),
    # event-driven coach driving issue -> merged-PR.
    "0002-coach-drives-lifecycle": ("issue-lifecycle", "drive-state-machine"),
    # substrate: author / admit / bind stages.
    "0003-author-substrate": ("substrate", "author-artifacts"),
    "0004-admit-substrate": ("substrate", "admit-packages"),
    "0005-bind-substrate": ("substrate", "bind-runtime"),
}

# #1400's trains (0006/0206/0306) retype under ``object-conflict-resolution`` but
# their per-path slugs are that issue's authoring decision (its trains are not in
# this branch). Documented, NOT fabricated here — #1400 extends the map when it
# lands. Kept out of ``aliases:`` so the resolver never maps a non-existent file.
DEFERRED_1400_SUBJECT = "object-conflict-resolution"

_ALIAS_FILE_REL = Path("plan") / "_trains" / "_aliases.yaml"
_TRAINS_DIR_REL = Path("plan") / "_trains"
_REGISTRY_REL = Path("plan") / "_trains.yaml"

# The legacy identity's second digit encoded the variant category. The typed
# grammar drops that digit and records the category as a FIELD; this map is the
# one-way projection digit -> field used by :func:`apply`. (#1421)
_CATEGORY_BY_DIGIT: Dict[str, str] = {
    "0": "nominal",
    "1": "error",
    "2": "alternate",
    "3": "exception",
}


def category_for_legacy(legacy_id: str) -> str:
    """Return the ``category`` FIELD for a legacy ``NNNN-slug`` id.

    The category is the legacy identity's second digit (``0`` nominal, ``1``
    error, ``2`` alternate, ``3`` exception). Defaults to ``"nominal"`` for any
    id that is not the canonical four-digit form.
    """
    if len(legacy_id) >= 2 and legacy_id[1] in _CATEGORY_BY_DIGIT:
        return _CATEGORY_BY_DIGIT[legacy_id[1]]
    return "nominal"


# ---------------------------------------------------------------------------
# Forward / rollback
# ---------------------------------------------------------------------------
def forward(legacy_id: str) -> str:
    """Return the typed ``train:<subject>:<slug>`` URN for *legacy_id*.

    Raises ``KeyError`` if the legacy id has no hand-authored alias — a loud
    failure is correct: an unmapped train must not be silently migrated.
    """
    subject, slug = LEGACY_TRAIN_ALIASES[legacy_id]
    return URNGrammar.train(subject, slug)  # engine builds + validates


def rollback(typed_urn: str) -> str:
    """Return the legacy ``NNNN-slug`` id for a typed URN (the inverse of
    :func:`forward`). Raises ``KeyError`` when the typed URN is unknown."""
    return build_inverse_map()[typed_urn]


def build_alias_map() -> Dict[str, str]:
    """Forward map ``{legacy-id: typed-urn}`` (built through the engine)."""
    return {legacy: forward(legacy) for legacy in LEGACY_TRAIN_ALIASES}


def build_inverse_map() -> Dict[str, str]:
    """Inverse map ``{typed-urn: legacy-id}``. Raises ``ValueError`` if two
    legacy ids collapse to one typed URN (the map would not be reversible)."""
    inverse: Dict[str, str] = {}
    for legacy, typed in build_alias_map().items():
        if typed in inverse:
            raise ValueError(
                f"alias map is not 1:1: {typed!r} maps from both "
                f"{inverse[typed]!r} and {legacy!r}"
            )
        inverse[typed] = legacy
    return inverse


def parse_alias_value(val) -> Optional[Tuple[str, str]]:
    """Parse an alias-file value into ``(subject, slug)``.

    Mirrors C2's ``TrainResolver._split_typed`` so the projected file and the
    resolver agree: tolerates a leading ``train:`` and both ``subject/slug`` and
    ``subject:slug`` separators.
    """
    if not isinstance(val, str):
        return None
    v = val.strip()
    if v.startswith("train:"):
        v = v[len("train:"):]
    parts = v.split("/", 1) if ("/" in v and ":" not in v) else v.split(":", 1)
    if len(parts) == 2 and parts[0] and parts[1]:
        return parts[0], parts[1]
    return None


# ---------------------------------------------------------------------------
# Projected data file (consumed by C2's TrainResolver)
# ---------------------------------------------------------------------------
def alias_file_document() -> dict:
    """The in-memory document written to ``plan/_trains/_aliases.yaml``.

    ``aliases:`` maps every legacy id to its ``subject/slug`` typed home — the
    shape C2's ``TrainResolver`` reads for dual-resolution.
    """
    return {
        "version": "1.0",
        "name": "Train URN alias map",
        "description": (
            "Migration alias map (#1421): legacy NNNN-slug -> typed "
            "train:<subject>:<slug>. Consumed by TrainResolver for legacy "
            "dual-resolution; inverse (rollback) is train_urn_migration.rollback()."
        ),
        "aliases": {
            legacy: f"{subject}/{slug}"
            for legacy, (subject, slug) in LEGACY_TRAIN_ALIASES.items()
        },
    }


def write_alias_file(root: Path) -> Path:
    """Project :func:`alias_file_document` to ``plan/_trains/_aliases.yaml``."""
    path = Path(root) / _ALIAS_FILE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(alias_file_document(), sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    return path


def load_alias_file(root: Path) -> Dict[str, Tuple[str, str]]:
    """Read ``plan/_trains/_aliases.yaml`` into ``{legacy-id: (subject, slug)}``."""
    path = Path(root) / _ALIAS_FILE_REL
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    aliases = raw.get("aliases") if isinstance(raw, dict) else None
    result: Dict[str, Tuple[str, str]] = {}
    for legacy, val in (aliases or {}).items():
        parsed = parse_alias_value(val)
        if parsed:
            result[legacy] = parsed
    return result


# ---------------------------------------------------------------------------
# Relocation (RUN LAST — after C2 resolver + C3 typed schema land)
# ---------------------------------------------------------------------------
def plan_relocations(root: Path) -> List[Tuple[Path, Path]]:
    """Return the list of ``(flat_src, nested_dst)`` moves the migration will
    perform — WITHOUT touching disk. Only flat legacy files that have a
    hand-authored alias are planned; anything else is left for a human.
    """
    trains_dir = Path(root) / _TRAINS_DIR_REL
    moves: List[Tuple[Path, Path]] = []
    if not trains_dir.exists():
        return moves
    for src in sorted(trains_dir.glob("*.yaml")):
        if src.name.startswith("_"):
            continue
        alias = LEGACY_TRAIN_ALIASES.get(src.stem)
        if not alias:
            continue
        subject, slug = alias
        dst = trains_dir / subject / f"{slug}.yaml"
        moves.append((src, dst))
    return moves


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
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    if isinstance(entry, dict) and entry.get("train_id"):
                        flat[entry["train_id"]] = entry
    elif isinstance(trains_data, list):
        for entry in trains_data:
            if isinstance(entry, dict) and entry.get("train_id"):
                flat[entry["train_id"]] = entry
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
    typed = forward(legacy_id)
    return existing.get(legacy_id) or existing.get(typed) or {}


def _rewrite_registry_typed(root: Path, existing: Dict[str, dict]) -> Path:
    """Project the typed ``plan/_trains.yaml``.

    Buckets are re-keyed ``trains: {<subject>: {<category>: [entries]}}``. Each
    entry carries the typed ``train_id``, the ``category`` field, the nested
    ``path``, and the ``wagons``/``description`` preserved from *existing*.
    """
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
    for group in trains:
        for section in trains[group]:
            trains[group][section].sort(key=lambda e: e["train_id"])
    return _write_registry(root, {"trains": trains})


# ---------------------------------------------------------------------------
# Destructive apply / revert (RUN LAST — after C2 resolver + C3 typed schema)
# ---------------------------------------------------------------------------
def apply(root: Path) -> List[Tuple[str, str, str]]:
    """Relocate every flat legacy train to its typed nested home and rewrite the
    registry. IDEMPOTENT: files already migrated are left in place.

    For each planned move:
      * read the flat ``NNNN-slug.yaml``,
      * set ``train_id`` to the typed ``train:<subject>:<slug>`` URN,
      * record ``category`` as a FIELD (retiring any ``category_digit``),
      * write ``plan/_trains/<subject>/<slug>.yaml`` and unlink the flat file.

    Then ``plan/_trains.yaml`` is re-projected subject-keyed. Returns the list of
    ``(typed_urn, subject, slug)`` migrated.
    """
    root = Path(root)
    trains_dir = root / _TRAINS_DIR_REL
    existing = _load_registry(root)

    migrated: List[Tuple[str, str, str]] = []
    for legacy_id, (subject, slug) in sorted(LEGACY_TRAIN_ALIASES.items()):
        typed = forward(legacy_id)
        src = trains_dir / f"{legacy_id}.yaml"
        dst = trains_dir / subject / f"{slug}.yaml"
        if src.exists():
            doc = yaml.safe_load(src.read_text(encoding="utf-8")) or {}
            doc["train_id"] = typed
            doc["category"] = category_for_legacy(legacy_id)
            doc.pop("category_digit", None)
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(
                yaml.safe_dump(doc, sort_keys=False, default_flow_style=False),
                encoding="utf-8",
            )
            src.unlink()
            migrated.append((typed, subject, slug))
        elif dst.exists():
            # already migrated on a prior run — idempotent no-op
            migrated.append((typed, subject, slug))

    _rewrite_registry_typed(root, existing)
    return migrated


def revert(root: Path) -> List[Tuple[str, str]]:
    """Inverse of :func:`apply`: restore every flat legacy train, drop the
    typed nesting, and rewrite the registry to its legacy digit-bucketed shape.

    Returns the list of ``(legacy_id, flat_path)`` restored.
    """
    root = Path(root)
    trains_dir = root / _TRAINS_DIR_REL
    existing = _load_registry(root)

    restored: List[Tuple[str, str]] = []
    for legacy_id, (subject, slug) in sorted(LEGACY_TRAIN_ALIASES.items()):
        dst = trains_dir / subject / f"{slug}.yaml"
        flat = trains_dir / f"{legacy_id}.yaml"
        if dst.exists():
            doc = yaml.safe_load(dst.read_text(encoding="utf-8")) or {}
            doc["train_id"] = legacy_id
            doc.pop("category", None)
            flat.write_text(
                yaml.safe_dump(doc, sort_keys=False, default_flow_style=False),
                encoding="utf-8",
            )
            dst.unlink()
            # prune the now-empty subject directory
            try:
                dst.parent.rmdir()
            except OSError:
                pass
            restored.append((legacy_id, str(flat)))

    _rewrite_registry_legacy(root, existing)
    return restored
