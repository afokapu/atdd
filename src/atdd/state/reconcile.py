"""`atdd state reconcile` — the M2 reconcile spine (#1400 CORE-012/013, spec §3).

The problem this solves: Dev A merges work to main; Dev B pulls, and B's local
store must pick up A's work **without losing B's uncommitted private authoring**.
The store is not the truth and the projection is not a backup of it — the relation
between them is exact (I3):

    store == hydrate(projection @ store_base_commit) + replay(local_overlay)

So reconcile is not "overwrite the store from the new projection". It is:

    if no overlay:          store := hydrate(incoming)
    else:                   back up
                            public  := hydrate(incoming)
                            store   := public + replay(overlay)
                            re-project affected objects
                            if replay invalid: stop, conflict report, keep backup
                            store_base_commit := new HEAD

**Reconcile is not overwrite (I5)** is the invariant with teeth. A store carrying
uncommitted overlay is *dirty*, and every path that would replace a dirty store
with a plain hydrate raises before touching sqlite (C001). Nothing is destroyed to
make room for incoming work.

The mechanism that makes non-destructiveness structural rather than careful: the
whole replay happens on a **copy** of the store, and the live ``state.sqlite`` is
replaced only once the replay is wholly valid. A conflicting reconcile therefore
leaves the store byte-identical by construction — there is no half-applied state to
roll back, because nothing was ever applied to the real store (R001, R002).

Same-object divergence conflicts *by design* (K001). If A merged a transition on an
object and B holds a different one, reconcile refuses and reports; it never resolves
by blind max-phase, because "further along" is not the same as "correct".

Dependency discipline: stdlib + ``atdd.state`` only. No provider is imported,
discovered or consulted — the entire path runs against a bare git remote.
"""
from __future__ import annotations

import logging
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from atdd.state import gitstore, metadata, overlay
from atdd.state.db import connect
from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.metadata import StoreBaseCommitError
from atdd.state.overlay import OverlayEvent
from atdd.state.paths import STATE_STORE_RELATIVE
from atdd.state.projection import (
    PROJECTION_RELATIVE,
    STATE_TOMBSTONED,
    build_document,
    hydrate,
    project,
)
from atdd.state.store import StateStore

_log = logging.getLogger(__name__)

#: The suffix marking a pre-mutation backup of the store. Retained on conflict —
#: it is the operator's undo, so reconcile never deletes one it wrote.
BACKUP_SUFFIX = ".bak"


class DirtyStoreError(RuntimeError):
    """An overwrite path was taken against a store carrying uncommitted overlay (C001).

    Names the overlay events that would have been lost. Raised **before** any sqlite
    mutation: the store is exactly as it was when this surfaces.
    """

    def __init__(self, message: str, *, events: Optional[List[OverlayEvent]] = None) -> None:
        self.events = events or []
        super().__init__(message)


class ColdStartError(StoreBaseCommitError):
    """The store carries overlay but has no base commit, so neither path can run (P002).

    This is the one state that would otherwise deadlock the operator: ``hydrate`` refuses
    because the store is dirty and sends them to ``reconcile``; ``reconcile`` refuses
    because there is no base commit and sends them back to ``hydrate``. Bouncing someone
    between two commands that each blame the other is not a refusal, it is a trap.

    So this refusal carries a way *out*: the private work has no anchor precisely because
    it was never shared, and the fix is to share it (project and commit) or to drop it —
    and the operator, not the tool, chooses which.
    """

    def __init__(self, events: List[OverlayEvent]) -> None:
        self.events = events
        super().__init__(
            f"the store carries {len(events)} uncommitted overlay event(s) but has no "
            "store_base_commit, so there is no public state to replay them onto.\n"
            "  This store cannot be hydrated (it would lose the work) or reconciled "
            "(there is no base).\n"
            "  To keep the work: `atdd state project` it, commit the projection, then "
            "`atdd state hydrate`.\n"
            "  To drop it: discard the overlay events, then `atdd state hydrate`.",
            commit=None,
        )


class ReplayConflictError(RuntimeError):
    """The overlay cannot be replayed onto the incoming projection (R002).

    Carries the :class:`ConflictReport`. The store is unchanged and the backup is
    retained; the operator resolves, they do not get resolved *for*.
    """

    def __init__(self, report: "ConflictReport") -> None:
        self.report = report
        super().__init__(report.render())


@dataclass(frozen=True)
class Conflict:
    """One overlay event the incoming projection will not accept."""

    event: OverlayEvent
    reason: str
    #: The incoming projection's state for the object, or ``None`` when it has none.
    incoming: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class ConflictReport:
    """Why the replay stopped, and what the operator can do about it (R002)."""

    conflicts: List[Conflict]
    backup_path: Optional[Path]
    base_commit: str
    head: str

    def render(self) -> str:
        """An actionable report: the offending events, the incoming state, the backup."""
        lines = [
            f"reconcile CONFLICT: the local overlay cannot be replayed onto {self.head[:12]}",
            f"  store_base_commit stays at {self.base_commit[:12]} — nothing was changed.",
            "",
        ]
        for conflict in self.conflicts:
            event = conflict.event
            lines.append(f"  ✗ {event.kind} on {event.object_uid} (event {event.event_id})")
            lines.append(f"      {conflict.reason}")
            if conflict.incoming is None:
                lines.append("      incoming projection: object absent")
            else:
                incoming = conflict.incoming
                lines.append(
                    f"      incoming projection: phase={incoming.get('phase')!r} "
                    f"state={incoming.get('state')!r}"
                )
        lines.append("")
        if self.backup_path is not None:
            lines.append(f"  A backup of your store is retained at: {self.backup_path}")
        lines.append(
            "  Resolve by re-authoring the offending change against the incoming state, "
            "or discard the overlay event."
        )
        return "\n".join(lines)


@dataclass(frozen=True)
class ReconcileResult:
    """What a reconcile did."""

    #: ``hydrate`` (no overlay) or ``replay`` (overlay replayed onto incoming).
    mode: str
    base_commit: str
    head: str
    hydrated: int = 0
    replayed: List[str] = field(default_factory=list)
    #: Events the incoming projection already carried — marked committed, not replayed.
    already_committed: List[str] = field(default_factory=list)
    #: The uids whose projection bytes moved.
    reprojected: List[str] = field(default_factory=list)
    backup_path: Optional[Path] = None

    def render(self) -> str:
        lines = [
            f"reconciled {self.base_commit[:12]} → {self.head[:12]} ({self.mode})",
            f"  hydrated {self.hydrated} object(s) from the incoming projection",
        ]
        if self.replayed:
            lines.append(f"  replayed {len(self.replayed)} overlay event(s)")
        if self.already_committed:
            lines.append(
                f"  {len(self.already_committed)} overlay event(s) already in the incoming "
                "projection — marked committed, not replayed"
            )
        if self.reprojected:
            lines.append(f"  re-projected {len(self.reprojected)} object(s)")
        if self.backup_path is not None:
            lines.append(f"  backup: {self.backup_path}")
        return "\n".join(lines)


@dataclass(frozen=True)
class StoreFreshness:
    """Whether the store's base commit still agrees with HEAD (M001)."""

    base_commit: Optional[str]
    head: str
    stale: bool

    def render(self) -> str:
        if self.base_commit is None:
            return (
                f"store has no store_base_commit (HEAD is {self.head[:12]}).\n"
                "  Run `atdd state hydrate` to anchor it."
            )
        if not self.stale:
            return f"store is fresh at {self.head[:12]}"
        return (
            f"store is STALE: store_base_commit is {self.base_commit[:12]} but "
            f"HEAD is {self.head[:12]}.\n"
            "  A HEAD-moving git operation ran without the ATDD hook. "
            "Run `atdd state reconcile`."
        )


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
def store_path(control_root: Path) -> Path:
    return Path(control_root) / STATE_STORE_RELATIVE


def projection_path(control_root: Path) -> Path:
    return Path(control_root) / PROJECTION_RELATIVE


def checkpoint(db_path: Path) -> None:
    """Fold the write-ahead log back into ``state.sqlite`` before it is copied.

    The store runs in WAL mode, so recent commits can still be sitting in
    ``state.sqlite-wal`` rather than in the database file itself. A plain file copy taken
    at that moment silently omits them — which would make a *backup* that is missing the
    very work it exists to protect, and a replay scratch copy that has quietly rewound.
    Checkpointing first makes the file a complete snapshot of the store.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()


def backup_store(db_path: Path) -> Path:
    """Copy ``state.sqlite`` aside before any mutation; return the backup path (C001).

    Never overwrites an existing backup — a second reconcile must not destroy the
    undo the first one left behind. The store is copied, not moved, so the live file
    is untouched by the act of backing it up.
    """
    db_path = Path(db_path)
    checkpoint(db_path)
    candidate = db_path.with_suffix(db_path.suffix + BACKUP_SUFFIX)
    counter = 1
    while candidate.exists():
        candidate = db_path.with_suffix(f"{db_path.suffix}{BACKUP_SUFFIX}.{counter}")
        counter += 1
    shutil.copy2(db_path, candidate)
    _log.info("state store backed up", extra={"backup": str(candidate)})
    return candidate


# --------------------------------------------------------------------------- #
# Hydrate — the anchored, dirty-gated entry point (P001, P002, C001)
# --------------------------------------------------------------------------- #
def resolve_head(repo: Path) -> Optional[str]:
    """HEAD, or ``None`` when the repository has no commits yet (P002).

    A checkout with no commits is a legitimate cold start — ``atdd init`` before the
    first commit — and hydrating there must work. There is simply no commit to anchor
    to, and pretending otherwise would stamp a lie.
    """
    try:
        return gitstore.head(repo)
    except gitstore.GitError:
        return None


def hydrate_store(
    control_root: Path,
    *,
    commit: Optional[str] = None,
    projection_dir: Optional[Path] = None,
) -> Tuple[int, Optional[str]]:
    """Hydrate the store from the committed projection and stamp its base commit.

    This is the *overwrite* path, and it is exactly where I5 has to bite: a store
    carrying uncommitted overlay would lose that work, so it raises
    :class:`DirtyStoreError` **before** touching sqlite and names the events that
    would have been lost (C001). A clean store hydrates with no backup and no fuss —
    including a cold start, where there is no store, no base commit, and possibly not
    even a first commit to anchor to (P002).

    Returns ``(objects_hydrated, base_commit)``; the commit is ``None`` on a
    repository that has no commits yet.
    """
    control_root = Path(control_root)
    repo = control_root
    resolved = resolve_head(repo) if commit is None else commit
    projection_dir = projection_path(control_root) if projection_dir is None else Path(projection_dir)

    from atdd.state.db import init_state_store  # local: keeps the import surface small

    db_path = init_state_store(start=control_root)
    conn = connect(db_path)
    try:
        events = overlay.replayable_events(conn)
        if events and metadata.base_commit(conn) is None:
            # Dirty AND unanchored: sending this operator to `reconcile` would just send
            # them back here. Refuse with a remedy instead of a round trip (P002).
            raise ColdStartError(events)
        if events:
            raise DirtyStoreError(
                f"refusing to overwrite a dirty store: {len(events)} uncommitted overlay "
                "event(s) would be lost — "
                + ", ".join(f"{e.kind} on {e.object_uid}" for e in events)
                + ". Run `atdd state reconcile` instead: it replays your overlay onto the "
                "incoming projection rather than discarding it.",
                events=events,
            )
        store = StateStore(conn)
        _replace_public_state(store, projection_dir)
        result = hydrate(projection_dir, store)
        if resolved is None:
            # Nothing to anchor to yet. Record the shape of the store, but do not
            # invent a base commit — reconcile would rather refuse than replay onto a
            # commit that never existed (P001-UNIT-002).
            metadata.mark_dirty(conn, False)
        else:
            metadata.stamp_base_commit(conn, resolved)
        return result.hydrated, resolved
    finally:
        conn.close()


def _replace_public_state(store: StateStore, projection_dir: Path) -> None:
    """Drop every work item the incoming projection does not carry.

    Hydrate *replaces* the public half; it does not merge into it. If it merged, an
    object the projection had dropped would linger in the store forever, and
    ``store == hydrate(projection)`` — the left half of I3 — would quietly stop being
    true. Safe to do unconditionally here: this path only ever runs against a clean
    store, and a purely local object is either in the overlay (so the store is dirty
    and we are not on this path) or already has a projection file of its own.
    """
    from atdd.state.projection import read_projection  # local: keeps the surface small

    incoming = read_projection(projection_dir)
    for obj in store.objects.list(kind=WORK_ITEM_KIND):
        if obj.uid not in incoming:
            store.objects.delete(obj.uid)


def freshness(control_root: Path, *, head: Optional[str] = None) -> StoreFreshness:
    """Is the store still anchored to HEAD? (M001)

    Hooks are convenience, never authority (spec §9): when one is bypassed the store
    is simply left behind HEAD, and the next ATDD command detects that here rather
    than silently trusting a stale public half.
    """
    control_root = Path(control_root)
    resolved = gitstore.head(control_root) if head is None else head
    conn = connect(store_path(control_root))
    try:
        base = metadata.base_commit(conn)
    finally:
        conn.close()
    return StoreFreshness(base_commit=base, head=resolved, stale=base != resolved)


# --------------------------------------------------------------------------- #
# Replay validation (R001, R002, K001) — does this event still apply?
# --------------------------------------------------------------------------- #
def _incoming_documents(projection_dir: Path) -> Dict[str, Dict[str, Any]]:
    from atdd.state.projection import read_projection  # local: keeps the surface small

    return read_projection(projection_dir)


def already_carried(incoming: Optional[Dict[str, Any]], event: OverlayEvent) -> bool:
    """True when the incoming projection already reflects ``event`` (Y001).

    This is what stops an event being replayed twice. Once a developer's own work comes
    back through the shared truth — projected, committed, merged, pulled — the incoming
    document already *is* that event's effect, and replaying it would apply the same
    intent a second time. So the event is marked committed and dropped instead.

    The test is per-kind rather than "would applying it change anything", because those
    are not the same question. Re-applying ``object_created`` would reset the phase to
    the value it was created at, so it *would* change the document — yet the create has
    plainly already reached the shared truth. What matters is whether the event's
    *intent* is satisfied, not whether its payload is idempotent.
    """
    if incoming is None:
        return False  # the object is still private; nothing was carried anywhere

    payload = event.payload
    if event.kind == overlay.OBJECT_CREATED:
        return True  # the uid is in the shared truth: the create landed
    if event.kind == overlay.PHASE_TRANSITION_REQUESTED:
        return incoming.get("phase") == payload.get("to_phase")
    if event.kind == overlay.BODY_UPDATED:
        return incoming.get("body") == payload.get("body")
    if event.kind == overlay.TRAIN_UPDATED:
        return incoming.get("train") == payload.get("train")
    if event.kind == overlay.WMBT_ADDED:
        return payload.get("wmbt") in (incoming.get("wmbts") or [])
    if event.kind == overlay.TOMBSTONE_REQUESTED:
        return incoming.get("state") == STATE_TOMBSTONED
    if event.kind == overlay.EXTERNAL_REF_APPLIED:
        refs = incoming.get("external_refs") or {}
        return refs.get(payload.get("provider")) == payload.get("ref")
    return False


def validate_event(
    current: Optional[Dict[str, Any]], event: OverlayEvent
) -> Optional[Conflict]:
    """The conflict ``event`` raises against ``current``, or ``None`` if it still applies.

    ``current`` is the state the event is about to be applied to: the incoming public
    state with every previously replayed event already on top of it. That distinction
    matters — an event editing an object the developer *created locally* is perfectly
    valid even though the shared truth has never heard of that object, because the
    create is sitting right there earlier in the same overlay.

    The rules are deliberately conservative. An event whose object the shared truth has
    since tombstoned no longer applies (R001). A phase transition whose *starting* phase
    disagrees is a same-object divergence: two people moved the same object from
    different places, and only they know which is right (K001). Nothing is auto-merged
    by taking the "further along" phase — that silently picks a winner.
    """
    if event.kind == overlay.OBJECT_CREATED:
        if current is not None:
            return Conflict(
                event=event,
                reason=(
                    "this uid already exists — a create cannot be replayed over an "
                    "object that is already there"
                ),
                incoming=current,
            )
        return None

    if current is None:
        return Conflict(
            event=event,
            reason=(
                f"{event.kind} targets {event.object_uid}, which neither the incoming "
                "projection nor the replayed overlay carries — the object it edits "
                "does not exist"
            ),
            incoming=None,
        )

    if current.get("state") == STATE_TOMBSTONED and event.kind != overlay.TOMBSTONE_REQUESTED:
        return Conflict(
            event=event,
            reason=(
                f"the incoming projection has TOMBSTONED {event.object_uid}, so "
                f"{event.kind} no longer applies to it"
            ),
            incoming=current,
        )

    if event.kind == overlay.PHASE_TRANSITION_REQUESTED:
        expected = event.payload.get("from_phase")
        actual = current.get("phase")
        if expected is not None and expected != actual:
            return Conflict(
                event=event,
                reason=(
                    f"same-object divergence: the transition was authored from phase "
                    f"{expected!r}, but the incoming projection has this object at "
                    f"{actual!r}. Two developers moved the same object from different "
                    "states; reconcile will not pick a winner by phase order"
                ),
                incoming=current,
            )

    return None


# --------------------------------------------------------------------------- #
# Reconcile (R001, R002, C001, Y001)
# --------------------------------------------------------------------------- #
def _scratch_copy(db_path: Path, workdir: Path) -> Path:
    """A working copy of the store. The live file is not touched until we succeed."""
    checkpoint(db_path)
    scratch = Path(workdir) / "state.sqlite"
    shutil.copy2(db_path, scratch)
    return scratch


def _replace_store(scratch: Path, db_path: Path) -> None:
    """Swap the successfully replayed copy into place, discarding WAL side files."""
    for sidecar in ("-wal", "-shm"):
        side = Path(str(db_path) + sidecar)
        if side.exists():
            side.unlink()
    shutil.move(str(scratch), str(db_path))


def reconcile(
    control_root: Path,
    *,
    head: Optional[str] = None,
    projection_dir: Optional[Path] = None,
) -> ReconcileResult:
    """Reconcile the local store with the projection at ``head`` (CORE-013).

    Raises :class:`StoreBaseCommitError` when the store is not anchored (P001),
    :class:`ReplayConflictError` when the overlay will not replay (R002). In both
    cases the store is left exactly as it was.
    """
    control_root = Path(control_root)
    db_path = store_path(control_root)
    projection_dir = projection_path(control_root) if projection_dir is None else Path(projection_dir)
    resolved_head = gitstore.head(control_root) if head is None else head

    conn = connect(db_path)
    try:
        # Anchor first: a baseless or unresolvable store is refused BEFORE any sqlite
        # mutation and before any projection is read (P001-UNIT-002).
        events = overlay.replayable_events(conn)
        if events and metadata.base_commit(conn) is None:
            raise ColdStartError(events)  # dirty AND unanchored — say how to get out
        base = metadata.require_base_commit(conn)
        if not gitstore.commit_exists(control_root, base):
            raise StoreBaseCommitError(
                f"the store's store_base_commit ({base}) is not a commit in this "
                "repository — the history it was hydrated from is gone. Run "
                "`atdd state hydrate` to re-anchor it; reconcile has no base to replay onto.",
                commit=base,
            )
    finally:
        conn.close()

    if not events:
        # Clean store: reconcile reduces to plain hydrate. No backup, nothing to lose.
        hydrated, _ = hydrate_store(
            control_root, commit=resolved_head, projection_dir=projection_dir,
        )
        _log.info(
            "reconciled by hydrate", extra={"base": base, "head": resolved_head},
        )
        return ReconcileResult(
            mode="hydrate", base_commit=base, head=resolved_head, hydrated=hydrated,
        )

    # Dirty store: back up BEFORE any mutation, then do the whole replay on a copy.
    backup = backup_store(db_path)
    with tempfile.TemporaryDirectory() as tmp:
        return _replay_onto_incoming(
            control_root=control_root,
            db_path=db_path,
            projection_dir=projection_dir,
            base=base,
            head=resolved_head,
            events=events,
            backup=backup,
            workdir=Path(tmp),
        )


def _replay_onto_incoming(
    *,
    control_root: Path,
    db_path: Path,
    projection_dir: Path,
    base: str,
    head: str,
    events: List[OverlayEvent],
    backup: Path,
    workdir: Path,
) -> ReconcileResult:
    """store := hydrate(incoming) + replay(overlay), on a copy, atomically (R001)."""
    incoming = _incoming_documents(projection_dir)
    scratch = _scratch_copy(db_path, workdir)
    conn = connect(scratch)
    try:
        store = StateStore(conn)

        # public := hydrate(incoming). Replace, do not merge: an object the incoming
        # projection does not carry is not public state, and the overlay — not a
        # leftover row — is what re-creates a purely local one.
        _replace_public_state(store, projection_dir)
        hydrated = hydrate(projection_dir, store).hydrated

        # ``working`` is the state each event is judged against: the incoming public
        # state, plus every event already replayed on top of it. An event editing a
        # locally-created object is valid precisely because its create is earlier in
        # this same overlay — judging against the incoming projection alone would
        # reject the private work this whole wagon exists to preserve.
        working: Dict[str, Optional[Dict[str, Any]]] = dict(incoming)

        conflicts: List[Conflict] = []
        replayed: List[str] = []
        committed: List[str] = []
        for event in events:
            uid = event.object_uid
            if already_carried(incoming.get(uid), event):
                committed.append(event.event_id)
                continue
            conflict = validate_event(working.get(uid), event)
            if conflict is not None:
                # Stop at the FIRST invalid event: everything queued behind it was
                # authored against a state that no longer exists, so its validity is
                # not merely unknown — it is unknowable.
                conflicts.append(conflict)
                break
            overlay.apply_event(conn, event)
            working[uid] = object_document(conn, uid)
            replayed.append(event.event_id)

        if conflicts:
            report = ConflictReport(
                conflicts=conflicts, backup_path=backup, base_commit=base, head=head,
            )
            _log.warning(
                "reconcile conflicted",
                extra={"base": base, "head": head, "conflicts": len(conflicts)},
            )
            # The partially replayed store is the scratch copy; it is discarded with
            # the temp directory and never persisted. state.sqlite never moved, so it
            # is byte-identical, and store_base_commit is still B (R001-UNIT-002).
            raise ReplayConflictError(report)

        # The replay was wholly valid. Record what the shared truth already had,
        # re-project, advance the anchor, and only THEN swap the copy into place.
        if committed:
            overlay.set_status(conn, committed, overlay.STATUS_COMMITTED)
        affected = _reproject(conn, store, projection_dir, events, replayed)
        metadata.stamp_base_commit(conn, head, dirty=bool(replayed))
    finally:
        conn.close()

    _replace_store(scratch, db_path)
    _log.info(
        "reconciled by replay",
        extra={"base": base, "head": head, "replayed": len(replayed)},
    )
    return ReconcileResult(
        mode="replay",
        base_commit=base,
        head=head,
        hydrated=hydrated,
        replayed=replayed,
        already_committed=committed,
        reprojected=affected,
        backup_path=backup,
    )


def _reproject(
    conn: sqlite3.Connection,
    store: StateStore,
    projection_dir: Path,
    events: List[OverlayEvent],
    replayed: List[str],
) -> List[str]:
    """Re-project the objects the replay touched (R001).

    ``project`` writes the whole store, which is a superset: an object the replay did
    not touch re-serialises to the bytes already on disk, because the projection is
    canonical (I1). So the *affected* set — the files whose bytes actually move — is
    exactly the objects the replayed events name, and that is what we report.
    """
    ids = set(replayed)
    affected = sorted({e.object_uid for e in events if e.event_id in ids})
    result = project(store, projection_dir)
    if affected:
        overlay.mark_projected(conn, result.digest)
    return affected


def object_document(conn: sqlite3.Connection, uid: str) -> Optional[Dict[str, Any]]:
    """The projection document a stored object would produce — for reports and tests."""
    obj = StateStore(conn).objects.get(uid)
    return None if obj is None else build_document(obj)
