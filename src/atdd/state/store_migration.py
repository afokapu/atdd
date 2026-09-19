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
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, FrozenSet, List

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
from atdd.state.store_contents import (
    StoreChangedDuringMigrationError,
    _data_version,
    replace_store_contents,
)
from atdd.state.projection import (
    ARCHIVED_PHASES,
    FIELD_TYPES,
    PHASES,
    STATE_ACTIVE,
    STRIPPED_AT_PROJECTION,
)
from atdd.state.store import Object, StateStore

_log = logging.getLogger(__name__)

#: Store-native defects — see :func:`inspect_store`.
DEFECT_MISSING_SLUG = "missing-slug"
DEFECT_UNPROJECTABLE_FIELD = "unprojectable-field"

#: What a store object's ``data`` bag may carry once migrated: exactly the contract's fields,
#: minus the two the projector supplies from columns rather than from the bag (``uid`` is the
#: row key, ``phase`` is ``objects.state``).
_PROJECTABLE_DATA_FIELDS = frozenset(FIELD_TYPES) - {"uid", "phase"}

#: Keys this migration DELETES from the store (#1622 dispositions).
#:
#: Drop is irreversible and the store is the only surviving source of truth, so each entry
#: is here because the evidence says nothing live reads it — not because it was unrecognised:
#:
#: - ``issue_number``  the authoritative linkage is ``external_refs``→uid, which lives in the
#:                     store; the bag copy is redundant and ``all_work_items()`` already
#:                     overwrites it. Ruled DROP with the CI-only ruling.
#: - ``_recovery``     forensic bags from the 2026-07-20 incident. Ruled DROP with the same
#:                     ruling; all 767 archived first to
#:                     ``docs/1400-findings/1622-recovery-bags-archive.json``. Seven carry
#:                     ``needs_operator_review: true`` and those reviews remain owed.
#: - ``worktree_path`` 130 carriers, every one an absolute host path. Cannot be grown: one
#:                     host path in a structured field refuses the whole projection.
#: - ``github_state``  } mirrored GitHub state with neither a bot keeping it fresh nor a
#: - ``labels``        } consumer reading it. Stale by construction.
#: - ``label_phase``   }
#: - ``merge_commit``  } null on every projectable carrier.
#: - ``closing_prs``   }
#: - ``archived``      0 projectable carriers.
#: - ``archetype``     no reader anywhere, tests included.
#: - ``archetypes``    1 carrier; flips to a relocation only on evidence operators still run
#:                     ``atdd update --archetypes``. None found.
#: - ``feature_urn``   4 carriers, no reader. It CONTRADICTS ``feature`` on 3 of its 5
#:                     objects; that evidence is preserved in
#:                     ``docs/1400-findings/1622-lab-remaining-five-keys.md``.
#: - ``file``          7 carriers, 0 non-null — pure null-seeding.
DROPPED_FROM_STORE: FrozenSet[str] = frozenset({
    "issue_number", "_recovery", "worktree_path", "github_state", "labels", "label_phase",
    "merge_commit", "closing_prs", "archived", "archetype", "archetypes", "feature_urn",
    "file",
})

#: A key the contract has no field for is a DEFECT only if no disposition covers it. The
#: three sets are disjoint by construction and the assertion below keeps them that way: a
#: key that was both stripped and dropped would have two answers to the same question.
_DISPOSITIONED = STRIPPED_AT_PROJECTION | DROPPED_FROM_STORE
assert not (STRIPPED_AT_PROJECTION & DROPPED_FROM_STORE), "a key cannot be both stripped and dropped"
assert not (_DISPOSITIONED & _PROJECTABLE_DATA_FIELDS), "a grown field needs no other disposition"


@dataclass(frozen=True)
class StoreMigrationReport:
    """What a completed :func:`migrate_store` run did."""

    #: old uid → the minted uid it now lives under.
    rekeyed: Dict[str, str] = field(default_factory=dict)
    #: uids that gained an ``owner_actor`` they did not carry.
    attributed: List[str] = field(default_factory=list)
    #: uid → the :data:`DROPPED_FROM_STORE` keys deleted from it. Recorded per object rather
    #: than counted: a drop is irreversible, so the report has to say what it took.
    dropped: Dict[str, List[str]] = field(default_factory=dict)
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
    (``additionalProperties: false``) **and no disposition covers it**. Still reported rather
    than stripped, and for the original reason: which keys to grow, strip or drop is a
    per-key decision with live readers on the other side of it, and a migration that decided
    silently would have taken ``wagon`` with it — read by two declared
    ``hot_path.DECISION_MODULES``, both behind ``except: return {}``, so nothing would raise.

    What changed (#1622) is that the decisions have now been made and written down, so the
    check subtracts them: ``wagon`` and ``type`` were grown into contract fields,
    :data:`~atdd.state.projection.STRIPPED_AT_PROJECTION` is omitted by the projector while
    the store keeps it, and :data:`DROPPED_FROM_STORE` is deleted here. A key outside all
    three is new since the dispositions were taken, and is exactly what this defect is for.
    """
    defects: List[MigrationDefect] = []
    if obj.state not in PHASES:
        defects.append(MigrationDefect(
            DEFECT_UNKNOWN_PHASE, index, slug, PHASE_KEY,
            f"phase {obj.state!r} is outside the lifecycle vocabulary "
            f"{[*PHASES, COMPLETE_PHASE]}",
        ))
    defects.extend(
        MigrationDefect(
            DEFECT_UNPROJECTABLE_FIELD, index, slug, key,
            f"the projection contract has no field {key!r} and forbids extra properties; "
            "it must be grown into a field, stripped at projection, or dropped — "
            "a migration may not decide that silently",
        )
        for key in sorted(set(obj.data) - _PROJECTABLE_DATA_FIELDS - _DISPOSITIONED)
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
    """``obj``'s data bag with its slug recorded, an owner guaranteed, and drops applied.

    :data:`DROPPED_FROM_STORE` is deleted here and nowhere else, so there is exactly one
    place where the store loses a key. The stripped set is NOT touched: those keys stay in
    the bag and the projector omits them.
    """
    data: Dict[str, Any] = {
        key: value for key, value in obj.data.items() if key not in DROPPED_FROM_STORE
    }
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
    dropped: Dict[str, List[str]] = {}
    untouched = 0
    for obj in store.objects.list(kind=WORK_ITEM_KIND):
        needs_owner = not obj.data.get("owner_actor")
        needs_uid = not is_uid(obj.uid)
        # A second run must still remove a dropped key that arrived since the first, so
        # "already migrated" cannot be decided on identity and ownership alone.
        needs_drop = bool(DROPPED_FROM_STORE & set(obj.data))
        if not needs_owner and not needs_uid and not needs_drop and obj.data.get(SLUG_KEY):
            untouched += 1
            continue
        if needs_drop:
            dropped[obj.uid] = sorted(DROPPED_FROM_STORE & set(obj.data))
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

    report = StoreMigrationReport(
        rekeyed=rekeyed, attributed=attributed, dropped=dropped, untouched=untouched,
    )
    _log.info(
        "state store migrated to contract-shaped identity",
        extra={
            "migrated": report.migrated, "attributed": len(attributed),
            "objects_with_drops": len(dropped), "untouched": untouched,
        },
    )
    return report


__all__ = [
    "DEFECT_MISSING_SLUG",
    "DEFECT_UNPROJECTABLE_FIELD",
    "DROPPED_FROM_STORE",
    "StoreChangedDuringMigrationError",
    "StoreMigrationReport",
    "inspect_store",
    "migrate_store",
]


# --------------------------------------------------------------------------- #
# The durable run — backup, scratch, replace the contents (#2024, #2031)
# --------------------------------------------------------------------------- #
class MigrationNotCleanError(Exception):
    """The migrated copy still does not inspect clean, so it was not swapped in."""

    def __init__(self, defects: List[MigrationDefect]) -> None:
        self.defects = list(defects)
        super().__init__(
            "the migrated store still does not inspect clean, so it was NOT swapped in:\n"
            + "\n".join(f"  {defect.render()}" for defect in self.defects)
        )


@dataclass(frozen=True)
class DurableMigrationResult:
    """What a durable run produced: the report, and the undo it left behind."""

    report: StoreMigrationReport
    backup: Path


def _migrate_the_copy(scratch: Path, *, owner_actor: str) -> StoreMigrationReport:
    """Migrate the working copy and judge the **result**, not merely the input.

    A migration that produced an unmigratable store must not be applied on the strength of
    having run, so ``inspect_store`` runs again over what came out.
    """
    from atdd.state.db import connect

    conn = connect(scratch)
    try:
        report = migrate_store(conn, owner_actor=owner_actor)
        leftover = inspect_store(StateStore(conn))
    finally:
        conn.close()
    if leftover:
        _log.warning(
            "migration produced a store that still does not inspect clean",
            extra={"scratch": str(scratch), "defects": len(leftover)},
        )
        raise MigrationNotCleanError(leftover)
    return report


def migrate_store_durably(
    db_path: Path, *, owner_actor: str = UNATTRIBUTED_OWNER,
) -> DurableMigrationResult:
    """Run :func:`migrate_store` so that a failure cannot cost the operator the store (#2024).

    :func:`migrate_store` writes per object — ``upsert`` and ``rekey`` each open their own
    ``with self._conn:`` — so there is no enclosing transaction, and dying mid-run would
    leave a half-migrated store indistinguishable from an unmigrated one. Wrapping the loop
    in an outer ``BEGIN`` does not compose: ``sqlite3``'s ``with conn:`` commits the
    *outermost* transaction, so the per-call managers commit it out from under the loop.

    So the work happens on a copy and the result is applied in one transaction (#2031):

    1. :func:`~atdd.state.reconcile.backup_store` — the **immutable** undo, never written to.
       Migrating *it* is the tempting shortcut and it destroys the undo: ``backup_store``
       returns the sole copy, so the "backup" ends up migrated and nothing holds the
       pre-migration store even on success. It is then **verified** by
       :func:`~atdd.state.store_checksum.verify_backup` — a table-level checksum against the
       pre-run store, not byte equality, because ``backup_store`` checkpoints the WAL before
       copying and the file legitimately differs. An unverifiable backup is not an undo, so
       the migration refuses rather than proceeding on the strength of one (#2029).
    2. :func:`~atdd.state.reconcile._scratch_copy` — the working copy, which is what gets
       migrated. A crash leaves it half-done and it is simply discarded.
    3. the result is re-inspected, then applied to the live store by
       :func:`~atdd.state.store_contents.replace_store_contents`.

    **Both copies are taken before the exclusive lock, deliberately.** They checkpoint the
    WAL on their own connections, and a checkpoint that contends with a fence this same
    process is holding waits out its full ``busy_timeout`` — twice, which held the lock for
    ~10.5s regardless of store size and timed out every concurrent writer by construction.
    The lock is now taken only for the replacement.

    That leaves the copy as a snapshot, so the apply is a compare-and-swap:
    ``PRAGMA data_version`` is read after the copy and again under the lock, and a change
    means another process wrote in between. Then this **refuses** rather than overwriting —
    :class:`StoreChangedDuringMigrationError`, with the live store untouched.

    **Known residual.** The snapshot and the baseline cannot be made simultaneous: the copy's
    own checkpoint bumps ``data_version``, so the baseline must follow the copy. A write
    committed in the gap between them is in neither — not in the snapshot, and already
    counted in the baseline — and would be overwritten. The gap is one ``PRAGMA`` read and
    the connection is opened beforehand to keep it that way, but it is not zero. Closing it
    properly means applying the migration as a delta rather than a wholesale replacement, so
    an untouched row is never rewritten at all.

    Raises :class:`LossyMigrationError` if an object cannot be migrated,
    :class:`MigrationNotCleanError` if the migrated copy does not inspect clean,
    :class:`~atdd.state.store_checksum.BackupVerificationError` if the backup cannot be
    proven faithful, and :class:`StoreChangedDuringMigrationError` if the store moved under
    us. In every case the live store is unchanged and the backup stands.
    """
    from atdd.state.db import connect
    from atdd.state.reconcile import _scratch_copy, backup_store
    from atdd.state.store_checksum import verify_backup

    db_path = Path(db_path)
    backup = backup_store(db_path)  # immutable undo, before anything is written
    verify_backup(db_path, backup)  # ...and proven to be one, before anything relies on it
    with tempfile.TemporaryDirectory() as tmp:
        # Open the live connection BEFORE the copy so that only a single pragma read sits
        # between the snapshot and the baseline. The baseline cannot be taken any earlier:
        # `backup_store` and `_scratch_copy` each checkpoint the WAL on their own
        # connections, and a checkpoint DOES bump `data_version` (measured 2 -> 3 -> 4), so
        # a baseline read before them would never match and every migration would refuse.
        live = connect(db_path)
        try:
            scratch = _scratch_copy(db_path, Path(tmp))
            expected = _data_version(live)
            report = _migrate_the_copy(scratch, owner_actor=owner_actor)
            replace_store_contents(live, scratch, expected_version=expected)
        finally:
            live.close()

    _log.info(
        "state store migrated durably",
        extra={"db_path": str(db_path), "backup": str(backup),
               "migrated": report.migrated},
    )
    return DurableMigrationResult(report=report, backup=backup)
