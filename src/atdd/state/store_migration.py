"""Store → contract-shaped identity (#1622 migrate-projection-authority, CORE-036).

The live migration. Its predecessor, :mod:`atdd.state.manifest_migration`, reads
``.atdd/manifest.yaml`` and cannot run at all: ``decommission-manifest`` (CORE-034) deleted
that file, so the manifest-keyed path has no input and identity has nowhere to come from.
This module takes the **store** as both source and target, because after CORE-034 the store
is the only surviving source of truth.

It lives apart from ``manifest_migration`` because the two are not variants of one job. That
module is the history of an artifact that no longer exists; this one is the path that runs.
Keeping them in one file made a 650-line module whose first half could not be executed —
and, less obviously, made it easy to read the dead half as though it were still the plan.

Two things happen to each work item, and nothing else:

- a slug-keyed object is **rekeyed** onto a freshly minted ``wi_<ULID>``, its former uid
  preserved as ``data.slug`` so every reference that named it still resolves;
- an object with no ``owner_actor`` gains one.

**Refuse before you write.** :func:`inspect_store` judges the whole store first, and a single
unmigratable object raises before the first write. That line is inherited from the manifest
migration (C001) and owes it a sharper debt here: this mutates the store *in place*, so a
partial run damages the only surviving source of truth rather than a derived tree — and a
half-migrated store cannot be told apart from an unmigrated one, leaving the operator no way
back.

Dependency discipline: stdlib + ``atdd.state``. No provider (I7). It reads no manifest, so it
is not — and must not become — a ``manifest_fallback`` reader.
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Dict, List

from atdd.state.identity import is_uid, mint_uid
from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.manifest_migration import (
    COMPLETE_PHASE,
    DEFECT_UNKNOWN_PHASE,
    PHASE_KEY,
    SLUG_KEY,
    UNATTRIBUTED_OWNER,
    LossyMigrationError,
    MigrationDefect,
)
from atdd.state.projection import ARCHIVED_PHASES, FIELD_TYPES, PHASES, STATE_ACTIVE
from atdd.state.store import Object, StateStore

_log = logging.getLogger(__name__)

#: Store-native defects — see :func:`inspect_store`.
DEFECT_MISSING_SLUG = "missing-slug"
DEFECT_UNPROJECTABLE_FIELD = "unprojectable-field"

#: What a store object's ``data`` bag may carry once migrated: exactly the contract's fields,
#: minus the two the projector supplies from columns rather than from the bag (``uid`` is the
#: row key, ``phase`` is ``objects.state``).
_PROJECTABLE_DATA_FIELDS = frozenset(FIELD_TYPES) - {"uid", "phase"}


@dataclass(frozen=True)
class StoreMigrationReport:
    """What a completed :func:`migrate_store` run did."""

    #: old uid → the minted uid it now lives under.
    rekeyed: Dict[str, str] = field(default_factory=dict)
    #: uids that gained an ``owner_actor`` they did not carry.
    attributed: List[str] = field(default_factory=list)
    #: Objects already carrying contract-shaped identity; left exactly as they were.
    untouched: int = 0

    @property
    def migrated(self) -> int:
        return len(self.rekeyed)

    def render(self) -> str:
        return "\n".join([
            f"migrated {self.migrated} work item(s) in the State Store",
            f"  minted identity     {self.migrated} object(s) rekeyed to wi_<ULID>",
            f"  attributed          {len(self.attributed)} object(s) gained an owner_actor",
            f"  already migrated    {self.untouched} object(s) left untouched",
        ])


def _slug_of(obj: Object) -> str:
    """The object's slug: its ``data`` slug, or its uid when the uid *is* the slug.

    A legacy object was keyed by its slug, so its uid is the only slug it ever had. An object
    whose uid is already contract-shaped has no such fallback — a ULID is not a slug — so one
    without ``data.slug`` genuinely has none, and that is a defect.
    """
    recorded = obj.data.get(SLUG_KEY)
    if recorded:
        return str(recorded)
    return "" if is_uid(obj.uid) else obj.uid


def _identity_defects(index: int, obj: Object, slug: str) -> List[MigrationDefect]:
    """Why ``obj``'s identity cannot be migrated. Judged for every object, archived included.

    Identity is a property of the *store*, not of the projection, so a ``COMPLETE`` object is
    held to this too — it still has to be findable by whatever named it.
    """
    if slug:
        return []
    return [MigrationDefect(
        DEFECT_MISSING_SLUG, index, obj.uid, SLUG_KEY,
        "no slug; the object's prior identity is unresolvable, so minting a uid for it "
        "would orphan every reference that named it",
    )]


def _projection_defects(index: int, obj: Object, slug: str) -> List[MigrationDefect]:
    """Why ``obj`` could not be projected after migrating. Projectable objects only.

    ``unknown-phase``: no legal projection document exists for it and inventing one is the
    lossy write C001 exists to prevent.

    ``unprojectable-field``: the ``data`` bag carries a key the contract has no field for
    (``additionalProperties: false``). Reported, deliberately, rather than stripped: which of
    these to grow into a real field, which to strip at projection and which to drop is a
    per-key decision with live readers on the other side of it (#1622 dispositions,
    ``docs/1400-findings/``), and a migration that dropped them silently would take ``wagon``
    with it — read by two declared ``hot_path.DECISION_MODULES``, both behind
    ``except: return {}``, so nothing would raise.
    """
    defects: List[MigrationDefect] = []
    if obj.state not in PHASES:
        defects.append(MigrationDefect(
            DEFECT_UNKNOWN_PHASE, index, slug, PHASE_KEY,
            f"phase {obj.state!r} is outside the lifecycle vocabulary "
            f"{list(PHASES) + [COMPLETE_PHASE]}",
        ))
    defects.extend(
        MigrationDefect(
            DEFECT_UNPROJECTABLE_FIELD, index, slug, key,
            f"the projection contract has no field {key!r} and forbids extra properties; "
            "it must be grown into a field, stripped at projection, or dropped — "
            "a migration may not decide that silently",
        )
        for key in sorted(set(obj.data) - _PROJECTABLE_DATA_FIELDS)
    )
    return defects


def inspect_store(store: StateStore) -> List[MigrationDefect]:
    """Every reason the store cannot be migrated and projected. ``[]`` means: safe to run.

    Pure — it writes nothing and returns the *whole* list, so :func:`migrate_store` can refuse
    in one piece and hand the operator every fix at once rather than one per run.

    Only **projectable** objects are judged on phase and fields: a ``COMPLETE`` object has no
    legal projection document by design (spec §18 decision 1), so the keys it carries cannot
    block a projection it was never part of. Every object is judged on its slug.
    """
    defects: List[MigrationDefect] = []
    for index, obj in enumerate(store.objects.list(kind=WORK_ITEM_KIND)):
        slug = _slug_of(obj)
        defects.extend(_identity_defects(index, obj, slug))
        if obj.state in ARCHIVED_PHASES:
            continue
        defects.extend(_projection_defects(index, obj, slug))
    return defects


def _migrated_data(obj: Object, slug: str, owner_actor: str) -> Dict[str, Any]:
    """``obj``'s data bag with its slug recorded and an owner guaranteed."""
    data: Dict[str, Any] = dict(obj.data)
    data[SLUG_KEY] = slug
    data.setdefault("owner_actor", owner_actor)
    data.setdefault("state", STATE_ACTIVE)
    return data


def migrate_store(
    conn: sqlite3.Connection,
    *,
    owner_actor: str = UNATTRIBUTED_OWNER,
) -> StoreMigrationReport:
    """Mint contract-shaped identity and an owner for every work item in the store (E002).

    ``owner_actor`` defaults to :data:`~atdd.state.manifest_migration.UNATTRIBUTED_OWNER`
    rather than a name: the contract requires the field, and naming a person nobody recorded
    would be a fabrication, not a default.

    Idempotent: an object already carrying a contract-shaped uid, a slug and an owner is left
    untouched, so a second run is a no-op and mints nothing.
    """
    store = StateStore(conn)
    defects = inspect_store(store)
    if defects:
        _log.warning(
            "refusing a lossy store migration; no object was mutated",
            extra={"defects": [d.render() for d in defects]},
        )
        raise LossyMigrationError(defects)

    rekeyed: Dict[str, str] = {}
    attributed: List[str] = []
    untouched = 0
    for obj in store.objects.list(kind=WORK_ITEM_KIND):
        needs_owner = not obj.data.get("owner_actor")
        needs_uid = not is_uid(obj.uid)
        if not needs_owner and not needs_uid and obj.data.get(SLUG_KEY):
            untouched += 1
            continue
        if needs_owner:
            attributed.append(obj.uid)
        store.objects.upsert(  # noqa: N+1 — one write per work item; a bulk migration
            obj.uid, WORK_ITEM_KIND, state=obj.state,
            data=_migrated_data(obj, _slug_of(obj), owner_actor),
        )
        if needs_uid:
            minted = mint_uid()
            store.objects.rekey(obj.uid, minted)  # noqa: N+1 — see above
            rekeyed[obj.uid] = minted

    report = StoreMigrationReport(rekeyed=rekeyed, attributed=attributed, untouched=untouched)
    _log.info(
        "state store migrated to contract-shaped identity",
        extra={"migrated": report.migrated, "attributed": len(attributed), "untouched": untouched},
    )
    return report


__all__ = [
    "DEFECT_MISSING_SLUG", "DEFECT_UNPROJECTABLE_FIELD", "StoreMigrationReport",
    "inspect_store", "migrate_store",
]
