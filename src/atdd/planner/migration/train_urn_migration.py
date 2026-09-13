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

import logging

import yaml

from atdd.coach.utils.graph.urn import URNGrammar

logger = logging.getLogger(__name__)

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
    # #1986: the CI-gate journey — one nominal path (0007) and its six
    # alternates (0201..0206), all one subject. ``extension-conventions`` is not
    # a style preference: ``is_durable_noun`` rejects ``enforce-conventions`` as
    # verb-led, so it is the only legal spelling of this subject. Slugs keep the
    # legacy wording (minus the digits) so the rename stays greppable; the slug
    # echoing the subject is accepted — see
    # ``train:documentation-obligation:prove-documentation-obligation``.
    "0007-enforce-extension-conventions": (
        "extension-conventions",
        "enforce-extension-conventions",
    ),
    "0201-enforce-strict-failure": ("extension-conventions", "enforce-strict-failure"),
    "0202-report-advisory-violation": (
        "extension-conventions",
        "report-advisory-violation",
    ),
    "0203-detect-unbound-declaration": (
        "extension-conventions",
        "detect-unbound-declaration",
    ),
    "0204-detect-succession-loss": ("extension-conventions", "detect-succession-loss"),
    "0205-detect-unrealized-obligation": (
        "extension-conventions",
        "detect-unrealized-obligation",
    ),
    "0206-decommission-orphan-detector": (
        "extension-conventions",
        "decommission-orphan-detector",
    ),
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
# Registry projection — lives in ``registry_projection`` (#1986).
#
# Only the three names ``apply``/``revert`` below actually call are imported.
# Everything else the split moved stays in that module and is imported from it
# directly by its callers, so this module re-exports nothing it does not use.
# ---------------------------------------------------------------------------
from .registry_projection import (  # noqa: E402  (placed after the data it consumes)
    _load_registry,
    _rewrite_registry_legacy,
    _rewrite_registry_typed,
)


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


def _restore_flat_train(legacy_id: str, dst: Path, flat: Path) -> None:
    """Rewrite one typed train back to its flat legacy file, then drop the typed
    file and prune its subject directory if that leaves it empty."""
    doc = yaml.safe_load(dst.read_text(encoding="utf-8")) or {}
    doc["train_id"] = legacy_id
    doc.pop("category", None)
    flat.write_text(
        yaml.safe_dump(doc, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    dst.unlink()
    try:
        dst.parent.rmdir()
    except OSError as exc:
        logger.debug(
            "revert: subject dir not empty, leaving in place",
            extra={"dir": str(dst.parent), "error": str(exc)},
        )


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
            _restore_flat_train(legacy_id, dst, flat)
            restored.append((legacy_id, str(flat)))

    _rewrite_registry_legacy(root, existing)
    return restored
