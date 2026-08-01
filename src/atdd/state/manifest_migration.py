"""Legacy manifest → committed projection (#1400 migrate-projection-authority, CORE-031).

.. note::

   **CORE-031 no longer has an input.** ``decommission-manifest`` (CORE-034) deleted
   ``.atdd/manifest.yaml``, so :func:`migrate` and :func:`mint_uids` — everything above the
   store-native section at the foot of this module — cannot run against a real repo. They are
   kept because they are the manifest's history and its tests still pin the refusal contract
   they established, not because anything reaches them.

   The live path is :func:`migrate_store` (CORE-036, #1622), which mints identity **in the
   State Store**, that being the only surviving source of truth. It inherits this module's one
   real idea — refuse the whole run before the first write — and owes it a sharper debt: it
   mutates the store in place, where the manifest migration only ever wrote a derived tree.

The one-way door. ``.atdd/manifest.yaml`` is a hand-editable ledger keyed by a **mutable slug**;
``.atdd/state/projection/<uid>.yaml`` is a derived, canonical document keyed by an **immutable
uid** (spec §10 rule 1). This module walks a repo across that gap: it reads the legacy manifest,
hydrates the store, and emits one deterministic projection file per work item — named by uid, and
never by slug, so a rename moves nothing (E001).

Two properties do all the work here.

**Refuse before you write (C001).** A manifest entry the tool cannot faithfully project — no uid,
a uid another entry already claimed, a phase outside the lifecycle vocabulary — aborts the *whole
run*, before the first file is written, and the report names **every** offending entry rather than
the first. A migration that half-succeeds leaves a projection tree that is neither the old truth
nor the new one, and the operator's next move (re-run? revert? hand-fix?) depends on facts the
tool destroyed on its way out. So it writes nothing, and it tells them everything.

**Mint identity separately, and record it (E001).** A uid minted *during* migration would be a
different uid on every run, and the second run would emit a second file for the same work item —
so the tool that promises byte-identical re-runs would be the tool that duplicates the corpus.
Identity is therefore backfilled by :func:`mint_uids` as its own recorded, committed step, writing
each ``uid`` back into the manifest; :func:`migrate` is strict and refuses an entry without one.
"Missing uid" is a defect precisely *because* silently inventing one is the lossy write C001 names.

Three shapes the migration deliberately does **not** carry across, each for a reason:

``issue_number`` → the store, never the projection
    The GitHub issue number is provider data. ``external_refs`` is owned by ``extension_bot``
    (``.atdd/policy/field-ownership.yaml``), so a *core* commit writing it is the wrong writer and
    the field-writer gate would refuse the migration commit — correctly. The number is preserved in
    the **store's** ``external_refs`` table, where :mod:`atdd.state.manifest_import` has always put
    it, and the mirror re-supplies it to the projection. That is the external-ref quarantine (I7)
    doing its job, not data being dropped.

``COMPLETE`` work items → archived, not projected
    ``COMPLETE`` is **derived** from merge-to-main (spec §18 decision 1) and may never be committed
    to a projection — :func:`atdd.state.projection.validate_document` refuses it. A completed work
    item therefore has no legal projection document, and inventing a phase for it ("it was probably
    SMOKE") is exactly the lossy write C001 exists to prevent. They are counted, listed, and left
    in the store; their completion lives in the merge commit that caused it. This is a **declared
    outcome, not a defect** — see :attr:`MigrationReport.archived`.

``owner_actor`` → defaulted, and said out loud
    The legacy manifest records no owner. The contract requires one. The tool defaults to
    :data:`UNATTRIBUTED_OWNER` rather than guessing a person, and ``--owner-actor`` sets it.

Dependency discipline: stdlib + ``pyyaml`` + ``atdd.state``. No provider (I7).
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import yaml

from atdd.state.identity import is_uid, mint_uid
from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND
from atdd.state.projection import (
    ARCHIVED_PHASES,
    FIELD_TYPES,
    PHASES,
    PROJECTION_RELATIVE,
    STATE_ACTIVE,
    ProjectionResult,
    assert_deterministic,
    project,
    validate_document,
)
from atdd.state.store import Object, StateStore

_log = logging.getLogger(__name__)

#: Where the legacy ledger lives, relative to the Control Root.
MANIFEST_RELATIVE = Path(".atdd") / "manifest.yaml"

#: The manifest's work-item list, and the keys that carry identity and phase.
SESSIONS_KEY = "sessions"
UID_KEY = "uid"
SLUG_KEY = "slug"
PHASE_KEY = "status"
ISSUE_KEY = "issue_number"

#: The phase a completed work item carries in the manifest — and may never carry in a projection
#: (spec §18 decision 1: COMPLETE is derived from merge-to-main). Not a defect: an outcome.
#: The projector agrees, and passes over such objects (``projection.ARCHIVED_PHASES``); the two
#: constants are bound by a test, because a migration that archived what the projector projected
#: (or vice versa) would produce a corpus that fails canonicality on its first run.
COMPLETE_PHASE = ARCHIVED_PHASES[0]

#: The owner a legacy entry has, which is none. Better a name that says so than an invented person.
UNATTRIBUTED_OWNER = "unattributed"

#: Manifest keys that become dedicated projection fields; everything else rides in the doc as-is,
#: minus the quarantined ones below.
_DIRECT_FIELDS = ("title", "body", "train")

#: Manifest keys the projection deliberately does not carry (see the module docstring).
_QUARANTINED = frozenset({ISSUE_KEY, UID_KEY, SLUG_KEY, PHASE_KEY})

#: Manifest bookkeeping the projection has no field for (``additionalProperties: false``).
_DROPPED = frozenset({"id", "file", "created", "archived", "type", "wagon", "feature",
                      "branch", "worktree", "worktree_path"})

DEFECT_MISSING_UID = "missing-uid"
DEFECT_DUPLICATE_UID = "duplicate-uid"
DEFECT_MALFORMED_UID = "malformed-uid"
DEFECT_UNKNOWN_PHASE = "unknown-phase"

#: Store-native defects (CORE-036) — see :func:`inspect_store`.
DEFECT_MISSING_SLUG = "missing-slug"
DEFECT_UNPROJECTABLE_FIELD = "unprojectable-field"


class MigrationError(RuntimeError):
    """The migration could not run at all (no manifest, unreadable YAML)."""


@dataclass(frozen=True)
class MigrationDefect:
    """One manifest entry the tool cannot faithfully project, and why."""

    rule: str
    index: int
    slug: str
    field: str
    reason: str

    def render(self) -> str:
        return (
            f"sessions[{self.index}] ({self.slug or '<no slug>'}): "
            f"[{self.rule}] field {self.field!r} — {self.reason}"
        )


class LossyMigrationError(MigrationError):
    """The manifest carries entries that cannot be projected. **Nothing was written** (C001).

    Carries *every* defect, not the first: an operator fixing a manifest wants the whole list, and
    a tool that reports one defect per run turns a five-minute fix into five runs.
    """

    def __init__(self, defects: Sequence[MigrationDefect]) -> None:
        self.defects = list(defects)
        super().__init__(
            f"refusing to migrate: {len(self.defects)} manifest entr(ies) cannot be projected, "
            "so no projection file was written:\n"
            + "\n".join(f"  {defect.render()}" for defect in self.defects)
        )


@dataclass(frozen=True)
class MigrationReport:
    """What a completed :func:`migrate` run did."""

    #: uid → the projection file written for it.
    files: Dict[str, Path] = field(default_factory=dict)
    #: The digest over the whole projected set.
    digest: str = ""
    #: COMPLETE work items: hydrated into the store, deliberately not projected (see docstring).
    archived: List[str] = field(default_factory=list)
    #: GitHub issue numbers preserved in the store's external_refs (never in the projection, I7).
    quarantined_refs: int = 0
    projection_dir: Optional[Path] = None

    @property
    def migrated(self) -> int:
        return len(self.files)

    def render(self) -> str:
        lines = [
            f"migrated {self.migrated} work item(s) → {self.projection_dir}",
            f"  digest              {self.digest}",
            f"  external refs       {self.quarantined_refs} quarantined in the store (I7)",
        ]
        if self.archived:
            lines.append(
                f"  archived            {len(self.archived)} COMPLETE work item(s), not projected "
                "(COMPLETE is derived from merge-to-main — spec §18 decision 1): "
                + ", ".join(sorted(self.archived))
            )
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Reading the legacy ledger
# --------------------------------------------------------------------------- #
def manifest_path(root: Path) -> Path:
    """The legacy manifest inside ``root``."""
    return Path(root) / MANIFEST_RELATIVE


def read_manifest(path: Path) -> Dict[str, Any]:
    """Read the legacy manifest, or raise :class:`MigrationError` naming the file."""
    path = Path(path)
    if not path.is_file():
        raise MigrationError(f"no legacy manifest to migrate: {path}")
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise MigrationError(f"{path} is not readable YAML: {exc}") from exc
    if not isinstance(document, dict):
        raise MigrationError(f"{path}: not a YAML mapping")
    return document


def sessions_of(document: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """The manifest's work-item entries (``[]`` when it has none)."""
    sessions = document.get(SESSIONS_KEY) or []
    if not isinstance(sessions, list):
        raise MigrationError(f"manifest {SESSIONS_KEY!r} is not a list")
    return [entry for entry in sessions if isinstance(entry, dict)]


# --------------------------------------------------------------------------- #
# The refusal (C001) — every defect, before any write
# --------------------------------------------------------------------------- #
def inspect(sessions: Sequence[Mapping[str, Any]]) -> List[MigrationDefect]:
    """Every reason ``sessions`` cannot be faithfully projected. ``[]`` means: safe to migrate.

    Pure. It writes nothing, opens nothing, and returns the *whole* list — so :func:`migrate` can
    refuse the run in one piece and hand the operator every fix at once.
    """
    defects: List[MigrationDefect] = []
    claimed: Dict[str, int] = {}

    for index, entry in enumerate(sessions):
        slug = str(entry.get(SLUG_KEY) or "")
        uid = entry.get(UID_KEY)

        if uid is None or uid == "":
            defects.append(MigrationDefect(
                DEFECT_MISSING_UID, index, slug, UID_KEY,
                "no uid; identity may not be invented during a migration (run `mint-uids` first, "
                "which records one in the manifest, so re-runs stay byte-identical)",
            ))
        elif not is_uid(uid):
            defects.append(MigrationDefect(
                DEFECT_MALFORMED_UID, index, slug, UID_KEY,
                f"uid {uid!r} is not a work-item uid (expected wi_<26-char ULID>)",
            ))
        elif uid in claimed:
            defects.append(MigrationDefect(
                DEFECT_DUPLICATE_UID, index, slug, UID_KEY,
                f"uid {uid} is already claimed by sessions[{claimed[uid]}]; a uid is globally "
                "unique and never reused (spec §10 rule 1)",
            ))
        else:
            claimed[str(uid)] = index

        phase = entry.get(PHASE_KEY)
        if phase not in PHASES and phase != COMPLETE_PHASE:
            defects.append(MigrationDefect(
                DEFECT_UNKNOWN_PHASE, index, slug, PHASE_KEY,
                f"phase {phase!r} is outside the lifecycle vocabulary "
                f"{list(PHASES) + [COMPLETE_PHASE]}",
            ))

    return defects


# --------------------------------------------------------------------------- #
# Identity backfill — its own recorded step, so migration stays idempotent
# --------------------------------------------------------------------------- #
def mint_uids(path: Path, *, entropy: Optional[bytes] = None) -> Tuple[int, Path]:
    """Backfill a uid into every manifest entry that lacks one; return ``(minted, path)``.

    This is a **recorded** write: the uid lands in the manifest and is committed. That is what
    makes :func:`migrate` idempotent — the identity is decided once, by this step, and every
    subsequent projection of that work item resolves to the same file. Minting inside ``migrate``
    would instead mint afresh on each run, and the "byte-identical re-run" E001 asks for would be
    a corpus that doubles every time it is migrated.

    Idempotent itself: an entry that already carries a well-formed uid is left exactly as it is.
    """
    path = Path(path)
    document = read_manifest(path)
    sessions = document.get(SESSIONS_KEY) or []
    minted = 0
    for entry in sessions:
        if not isinstance(entry, dict):
            continue
        if is_uid(entry.get(UID_KEY)):
            continue
        entry[UID_KEY] = mint_uid(entropy=entropy)
        minted += 1

    if minted:
        path.write_text(
            yaml.safe_dump(document, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
    _log.info(
        "minted work-item uids into the legacy manifest",
        extra={"manifest": str(path), "minted": minted, "entries": len(sessions)},
    )
    return minted, path


# --------------------------------------------------------------------------- #
# Entry → projection document
# --------------------------------------------------------------------------- #
def build_document(entry: Mapping[str, Any], *, owner_actor: str = UNATTRIBUTED_OWNER) -> Dict[str, Any]:
    """The projection document for one manifest entry — pure, total, and quarantine-aware.

    Everything the contract has a field for is carried across. ``issue_number`` is **not** (it is
    the provider's, and core is not its writer); nor is the manifest's own bookkeeping, for which
    the contract has no field and ``additionalProperties: false``.
    """
    document: Dict[str, Any] = {
        "uid": str(entry[UID_KEY]),
        "phase": str(entry[PHASE_KEY]),
        "state": STATE_ACTIVE,
        "owner_actor": str(entry.get("owner_actor") or owner_actor),
        "slug": str(entry.get(SLUG_KEY) or ""),
    }
    for key in _DIRECT_FIELDS:
        value = entry.get(key)
        if value is not None:
            document[key] = value
    document.setdefault("wmbts", [])
    # Anything the manifest carried that the contract still has a field for rides along; the
    # quarantined and the unmappable do not.
    for key, value in entry.items():
        if key in _QUARANTINED or key in _DROPPED or key in document:
            continue
        document[key] = value
    return document


def build_documents(
    sessions: Sequence[Mapping[str, Any]], *, owner_actor: str = UNATTRIBUTED_OWNER,
) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    """``(projectable documents by uid, archived COMPLETE uids)`` — validated, nothing written.

    Refuses the whole set if any document breaks the contract or leaks nondeterministic content,
    for the same reason :func:`migrate` refuses the whole run: a half-valid corpus is worse than
    a refused one.
    """
    documents: Dict[str, Dict[str, Any]] = {}
    archived: List[str] = []
    for entry in sessions:
        uid = str(entry[UID_KEY])
        if entry.get(PHASE_KEY) == COMPLETE_PHASE:
            archived.append(uid)
            continue
        document = build_document(entry, owner_actor=owner_actor)
        assert_deterministic(document, uid=uid)
        validate_document(document)
        documents[uid] = document
    return documents, archived


# --------------------------------------------------------------------------- #
# The migration (E001)
# --------------------------------------------------------------------------- #
def hydrate_store(
    store: StateStore,
    sessions: Sequence[Mapping[str, Any]],
    *,
    owner_actor: str = UNATTRIBUTED_OWNER,
) -> int:
    """Write every work item into the store, uid-keyed; return the external refs quarantined.

    The GitHub issue number goes into the store's ``external_refs`` table and **not** into the
    projection: it is the provider's data, the bot is its declared writer, and core writing it into
    a committed document would be the wrong writer touching a field it does not own (§7.1). The
    store is where it is preserved, and the quarantine is where it stays (I7).
    """
    refs = 0
    for entry in sessions:
        uid = str(entry[UID_KEY])
        document = build_document(entry, owner_actor=owner_actor)
        data = {k: v for k, v in document.items() if k not in ("uid", "phase")}
        store.objects.upsert(  # noqa: N+1 — one upsert per work item; a bulk migration, not a query loop
            uid, WORK_ITEM_KIND, state=str(entry[PHASE_KEY]), data=data,
        )
        issue = entry.get(ISSUE_KEY)
        if issue is None:
            continue
        store.external_refs.link(  # noqa: N+1 — see above
            uid, GITHUB_PROVIDER, "issue", str(issue), data={"source": "manifest-migration"},
        )
        refs += 1
    return refs


def migrate(
    root: Path,
    *,
    store: Optional[StateStore] = None,
    out_dir: Optional[Path] = None,
    owner_actor: str = UNATTRIBUTED_OWNER,
) -> MigrationReport:
    """Migrate ``root``'s legacy manifest into the committed projection (C001 + E001).

    The order is the contract: **inspect the whole manifest, refuse the whole run, then write.**
    :class:`LossyMigrationError` is raised before a single file is created, so a manifest with one
    bad entry leaves the projection directory exactly as it found it.

    Deterministic: run it twice against the same manifest and the second run reproduces the first
    byte for byte (I1), because the uid — the only thing that names a file — was decided by
    :func:`mint_uids` and recorded, not re-rolled here.
    """
    root = Path(root)
    document = read_manifest(manifest_path(root))
    sessions = sessions_of(document)

    defects = inspect(sessions)
    if defects:
        _log.warning(
            "refusing a lossy migration; no projection file was written",
            extra={"root": str(root), "defects": [d.render() for d in defects]},
        )
        raise LossyMigrationError(defects)

    documents, archived = build_documents(sessions, owner_actor=owner_actor)
    projection_dir = Path(out_dir) if out_dir is not None else root / PROJECTION_RELATIVE

    with _store_or(store, root) as active:
        refs = hydrate_store(active, sessions, owner_actor=owner_actor)
        result: ProjectionResult = project(active, projection_dir)

    report = MigrationReport(
        files=dict(result.files), digest=result.digest, archived=sorted(archived),
        quarantined_refs=refs, projection_dir=projection_dir,
    )
    _log.info(
        "legacy manifest migrated to the committed projection",
        extra={"root": str(root), "migrated": report.migrated,
            "archived": len(report.archived), "refs": refs, "digest": report.digest},
    )
    return report


# --------------------------------------------------------------------------- #
# The store-native migration (CORE-036, #1622) — the manifest is gone
# --------------------------------------------------------------------------- #
#: What a store object's ``data`` bag is allowed to carry once migrated: exactly the
#: contract's fields, minus the two the projector supplies from columns rather than
#: from the bag (``uid`` is the row key, ``phase`` is ``objects.state``).
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

    A legacy object was keyed by its slug, so its uid is the only slug it ever had. An
    object whose uid is already contract-shaped has no such fallback — a ULID is not a
    slug — so one without ``data.slug`` genuinely has none, and that is a defect.
    """
    recorded = obj.data.get(SLUG_KEY)
    if recorded:
        return str(recorded)
    return "" if is_uid(obj.uid) else obj.uid


def inspect_store(store: StateStore) -> List[MigrationDefect]:
    """Every reason the store cannot be migrated and projected. ``[]`` means: safe to run.

    Pure — it writes nothing and returns the *whole* list, so :func:`migrate_store` can
    refuse in one piece. Three kinds of defect, each for a different reason:

    ``missing-slug``
        The object has no resolvable prior identity. Identity is about to move to a minted
        uid, and the slug is the only thing that still connects the new uid to every branch
        name, worktree and reference that named the old one. Migrating without it does not
        lose a display string — it orphans the object.

    ``unknown-phase``
        The lifecycle phase is outside the vocabulary, so no legal projection document can
        be built for it and inventing one is the lossy write C001 exists to prevent.

    ``unprojectable-field``
        The ``data`` bag carries a key the contract has no field for
        (``additionalProperties: false``). Reported, deliberately, rather than stripped:
        which of these to grow into a real field, which to strip at projection and which to
        drop outright is a per-key decision with live readers on the other side of it (#1622
        dispositions), and a migration that silently dropped them would take `wagon` — read
        by two declared ``hot_path.DECISION_MODULES``, both behind ``except: return {}`` —
        with it, and nothing would raise.

    Only **projectable** objects are judged on phase and fields: a ``COMPLETE`` object has
    no legal projection document by design (spec §18 decision 1), so the keys it carries
    cannot block a projection it was never part of. Every object is judged on its slug,
    because identity is a property of the store, not of the projection.
    """
    defects: List[MigrationDefect] = []
    for index, obj in enumerate(store.objects.list(kind=WORK_ITEM_KIND)):
        slug = _slug_of(obj)
        if not slug:
            defects.append(MigrationDefect(
                DEFECT_MISSING_SLUG, index, obj.uid, SLUG_KEY,
                "no slug; the object's prior identity is unresolvable, so minting a uid for "
                "it would orphan every reference that named it",
            ))
        if obj.state in ARCHIVED_PHASES:
            continue
        if obj.state not in PHASES:
            defects.append(MigrationDefect(
                DEFECT_UNKNOWN_PHASE, index, slug, PHASE_KEY,
                f"phase {obj.state!r} is outside the lifecycle vocabulary "
                f"{list(PHASES) + [COMPLETE_PHASE]}",
            ))
        for key in sorted(set(obj.data) - _PROJECTABLE_DATA_FIELDS):
            defects.append(MigrationDefect(
                DEFECT_UNPROJECTABLE_FIELD, index, slug, key,
                f"the projection contract has no field {key!r} and forbids extra properties; "
                "it must be grown into a field, stripped at projection, or dropped — "
                "a migration may not decide that silently",
            ))
    return defects


def migrate_store(
    conn: sqlite3.Connection,
    *,
    owner_actor: str = UNATTRIBUTED_OWNER,
) -> StoreMigrationReport:
    """Mint contract-shaped identity and an owner for every work item **in the store** (E002).

    The store-native successor to :func:`migrate`. That one reads ``.atdd/manifest.yaml``
    and cannot run at all: ``decommission-manifest`` deleted the file, so the manifest-keyed
    path has no input and identity has nowhere to come from. This one takes the store as
    both source and target, because the store is now the only surviving source of truth.

    Two things happen to each object, and nothing else:

    - a slug-keyed object is **rekeyed** to a freshly minted ``wi_<ULID>``, with its former
      uid preserved as ``data.slug`` so every reference that named it still resolves
      (:meth:`~atdd.state.store.ObjectStore.rekey` carries its refs, events and edges over);
    - an object with no ``owner_actor`` gains one — ``UNATTRIBUTED_OWNER`` by default,
      because the contract requires the field and naming a person nobody recorded would be
      a fabrication, not a default.

    **Refuse before you write.** :func:`inspect_store` judges the whole store first, and a
    single unmigratable object raises :class:`LossyMigrationError` before the first write.
    That line matters more here than it did for the manifest: this migration mutates the
    store *in place*, so a partial run damages the only surviving source of truth rather
    than a derived tree — and a half-migrated store cannot be told apart from an unmigrated
    one, leaving the operator no way back.

    Idempotent: an object already carrying a contract-shaped uid and an owner is left
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
        data = dict(obj.data)
        needs_owner = not data.get("owner_actor")
        needs_uid = not is_uid(obj.uid)
        if not needs_owner and not needs_uid and data.get(SLUG_KEY):
            untouched += 1
            continue
        data[SLUG_KEY] = _slug_of(obj)
        if needs_owner:
            data["owner_actor"] = owner_actor
            attributed.append(obj.uid)
        data.setdefault("state", STATE_ACTIVE)
        store.objects.upsert(  # noqa: N+1 — one write per work item; a bulk migration
            obj.uid, WORK_ITEM_KIND, state=obj.state, data=data,
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


class _store_or:  # noqa: N801 — a context-manager helper, used as `with _store_or(...)`
    """Use the caller's store, or open the repo's own for the duration of the run."""

    def __init__(self, store: Optional[StateStore], root: Path) -> None:
        self._given = store
        self._root = root
        self._conn: Optional[sqlite3.Connection] = None

    def __enter__(self) -> StateStore:
        if self._given is not None:
            return self._given
        from atdd.state.db import connect, init_state_store

        self._conn = connect(init_state_store(start=self._root))
        return StateStore(self._conn)

    def __exit__(self, *_exc: Any) -> None:
        if self._conn is not None:
            self._conn.close()


__all__ = [
    "COMPLETE_PHASE", "DEFECT_DUPLICATE_UID", "DEFECT_MALFORMED_UID", "DEFECT_MISSING_SLUG",
    "DEFECT_MISSING_UID", "DEFECT_UNKNOWN_PHASE", "DEFECT_UNPROJECTABLE_FIELD",
    "LossyMigrationError", "MANIFEST_RELATIVE", "MigrationDefect",
    "MigrationError", "MigrationReport", "PHASE_KEY", "SESSIONS_KEY", "SLUG_KEY",
    "StoreMigrationReport", "UID_KEY", "UNATTRIBUTED_OWNER", "build_document",
    "build_documents", "hydrate_store", "inspect", "inspect_store", "manifest_path",
    "migrate", "migrate_store", "mint_uids", "read_manifest", "sessions_of",
]
