"""`atdd state reconcile` — the M2 reconcile spine (#1400 CORE-012/013, spec §3).

The problem this solves: Dev A merges work to main; Dev B pulls, and B's local
store must pick up A's work **without losing B's uncommitted private authoring**.
The store is not the truth and the projection is not a backup of it. The relation
between them (I3) is:

    store == hydrate(projection @ store_base_commit) + replay(local_overlay)

**over the objects the projection mentions.** That qualifier is not a footnote; it
was added at the cost of ~588 work_items (#1580). I3 used to be read as an exact
equality in both directions, which made a *gap* in the projection into an
instruction: an object the projection did not carry was deleted, because otherwise
the left half would stop being true. But the projection at HEAD is only known to be
complete when something establishes that, and nothing ever did — a gitignored
projection, a shallow clone, an older branch, or a Control Root resolved one
directory off each omits objects while asserting nothing whatever about them. On
2026-07-20 that inference emptied the store in a single silent operation.

So absence means **no information**, and I3 holds in the only form it was ever
entitled to: the projection is authoritative for what it says, and silent about
what it does not. Retirement must be stated — a committed tombstone carrying actor,
reason, source generation and prior-object digest — and even then it is a record
rather than a removal; physical deletion belongs to ``tombstone.compact_archive``
alone. See :func:`_replace_public_state`.

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

I5 guarded the *dirty* store and only the dirty store, which is why it stayed
silent through the incident: the store that lost 588 objects was clean, and "a
clean store hydrates with no backup and no fuss" was true and catastrophic at the
same time. The guards added in #1580 judge the incoming projection instead of the
local overlay, so they fire on exactly the case I5 was never watching:

- an **absent** projection is refused, and refused loudly when a populated store is
  at stake — it is the absence of an assertion, not an assertion of absence;
- an **empty** projection never empties a populated store;
- a projection retiring an implausible share of the store in one reconcile is
  refused past a blast radius, with an operator override that asserts the expected
  count rather than forcing past the check (:func:`guard_deletions`);
- a store whose Control Root is not the checkout it follows will not follow any
  HEAD at all (:func:`assert_reconcilable`).

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

#: Deletions at or below this count are routine and never refused, whatever proportion
#: of the store they represent (#1580). Retiring 2 objects from a store of 6 is a third
#: of it and is also an ordinary Tuesday; a guard that refuses Tuesdays is one operators
#: learn to route around, and a routed-around guard protects nothing.
SAFE_DELETIONS = 5

#: Above :data:`SAFE_DELETIONS`, the largest share of the work_items one reconcile may
#: remove. Catches the small store, where a catastrophe is not a large *number*: half of
#: a 20-object store is 10 objects and the whole of somebody's month.
MAX_DELETION_FRACTION = 0.25

#: …and the largest absolute count, however small the share. Catches the large store,
#: where 60 objects out of 5000 is a rounding error proportionally and still 60 things
#: somebody has to get back.
MAX_ABSOLUTE_DELETIONS = 50


class DirtyStoreError(RuntimeError):
    """An overwrite path was taken against a store carrying uncommitted overlay (C001).

    Names the overlay events that would have been lost. Raised **before** any sqlite
    mutation: the store is exactly as it was when this surfaces.
    """

    def __init__(self, message: str, *, events: Optional[List[OverlayEvent]] = None) -> None:
        self.events = events or []
        super().__init__(message)


class MassDeletionRefused(RuntimeError):
    """A reconcile would have removed more store state than any guard will allow (#1580).

    Same posture as :class:`DirtyStoreError` and for the same reason: raised **before** any
    sqlite mutation, so the store is exactly as it was when this surfaces. It carries the
    arithmetic — how many objects exist, how many were doomed, which rule tripped — because
    the number is what tells an operator whether they are looking at a misconfiguration or
    at a genuine mass retirement, and those need opposite responses.
    """

    def __init__(
        self,
        message: str,
        *,
        doomed: Optional[List[str]] = None,
        existing: int = 0,
        allowed: Optional[int] = None,
    ) -> None:
        #: The uids that would have been removed.
        self.doomed = list(doomed or [])
        #: How many work_items the store held when the guard ran.
        self.existing = existing
        #: The count the operator asserted via ``allow_deletions``, if any.
        self.allowed = allowed
        super().__init__(message)


class SharedStoreReconcileRefused(RuntimeError):
    """The store's Control Root is not the checkout whose HEAD it was asked to follow (#1580).

    In the flat-sibling layout the Control Root resolves to the *project root* — the parent
    of the primary ``main/`` checkout — and every worktree shares the one store beneath it
    (``paths.resolve_control_root`` rule 1.5). That directory is not a git repository: no
    HEAD, no branch, no commits. The worktrees around it have their own, one each.

    Reconcile is defined against a commit. For a store whose Control Root is not a checkout
    there is no such commit, so it was resolving one from whichever worktree happened to
    invoke it — which makes the shared store's contents a function of which arbitrary HEAD
    moved last, and lets an older feature branch roll every other worktree's view backward.

    Whether ownership should be per-worktree or a single daemon is still open; a store
    answering to a HEAD that does not describe it is wrong under either answer, so it is
    refused now.
    """

    def __init__(self, control_root: Path) -> None:
        self.control_root = Path(control_root)
        super().__init__(
            f"refusing to reconcile the store at {self.control_root}: its Control Root is "
            "not a git checkout, so no HEAD describes it.\n"
            "  This is the shared project-root store of a flat-sibling worktree layout. It "
            "is shared by every worktree, and reconciling it against any one worktree's "
            "HEAD makes its contents depend on which checkout moved last — an older branch "
            "would roll back work that every other worktree can see.\n"
            "  Reconcile from a Control Root that is itself the checkout it follows, or set "
            "ATDD_CONTROL_ROOT to one. Nothing has been changed."
        )


def assert_reconcilable(control_root: Path) -> None:
    """Refuse a Control Root that is not itself the git checkout it would follow (#1580).

    Deliberately narrow, and shaped as the *positive* case rather than a layout sniff: the
    Control Root must carry its own ``.git``. That is precisely the single-repo layout that
    ships to consumers and the one every hermetic fixture builds, so nothing legitimate is
    refused; and it is precisely what the shared project-root store is not.
    """
    control_root = Path(control_root)
    git_entry = control_root / ".git"
    if git_entry.is_dir() or git_entry.is_file():
        return
    _log.warning(
        "reconcile refused: control root is not a git checkout",
        extra={"control_root": str(control_root)},
    )
    raise SharedStoreReconcileRefused(control_root)


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
    except gitstore.GitError as exc:
        _log.info(
            "repository has no HEAD; treating as a cold start",
            extra={"repo": str(repo), "error": str(exc)},
        )
        return None


def hydrate_store(
    control_root: Path,
    *,
    commit: Optional[str] = None,
    projection_dir: Optional[Path] = None,
    allow_deletions: Optional[int] = None,
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
    # Before anything else: is this store even entitled to follow this HEAD? (#1580)
    assert_reconcilable(control_root)
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
        _replace_public_state(store, projection_dir, allow_deletions=allow_deletions)
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


def guard_deletions(
    doomed: List[str], *, existing: int, allow_deletions: Optional[int] = None
) -> None:
    """Refuse a deletion set that is too large to be believable (#1580).

    This is the guard that does not care *why* the deletion set was computed. C002-UNIT-004
    removes the specific path that emptied the store — absence stops meaning deletion — but
    that is not the same as removing the class: a mass tombstone, an over-eager compaction,
    a badly resolved merge, or a Control Root pointed at the wrong project all arrive at the
    same raw ``DELETE`` loop by a different road. So the count itself is judged, wherever it
    came from.

    Three rules, in the order they are applied:

    1. At or below :data:`SAFE_DELETIONS`, nothing is refused (see the constant for why).
    2. Above it, more than :data:`MAX_DELETION_FRACTION` of the work_items is refused.
    3. And more than :data:`MAX_ABSOLUTE_DELETIONS` is refused however small the share.

    ``allow_deletions`` is the way through, and it is an **assertion, not a force flag**:
    the operator states how many deletions they expect, and a number that does not match
    reality is refused as firmly as no number at all. ``--force`` answers "do it anyway",
    which is the question nobody was asked on 2026-07-20; this asks "how many?", and a wrong
    answer is proof the operator does not yet know what they are about to do.
    """
    count = len(doomed)
    if count == 0:
        return

    if allow_deletions is not None and allow_deletions != count:
        raise MassDeletionRefused(
            f"refusing to retire {count} work_item(s): you asserted --allow-deletions "
            f"{allow_deletions}, but this reconcile would retire {count}. The numbers must "
            "match — if they do not, the reconcile is not the one you think it is.\n"
            f"  Objects at stake: {_render_uids(doomed)}",
            doomed=doomed, existing=existing, allowed=allow_deletions,
        )

    if count <= SAFE_DELETIONS:
        return  # routine retirement; the proportional rule must not make tiny stores unusable

    if allow_deletions == count:
        _log.warning(
            "mass deletion allowed by explicit operator assertion",
            extra={"deletions": count, "existing": existing},
        )
        return

    share = (count / existing) if existing else 1.0
    tripped = None
    if count > MAX_ABSOLUTE_DELETIONS:
        tripped = (
            f"{count} exceeds the absolute limit of {MAX_ABSOLUTE_DELETIONS} retirements "
            "in one reconcile"
        )
    elif share > MAX_DELETION_FRACTION:
        tripped = (
            f"{count} of {existing} work_item(s) is {share:.0%} of the store, over the "
            f"{MAX_DELETION_FRACTION:.0%} limit for a single reconcile"
        )
    if tripped is None:
        return

    _log.warning(
        "reconcile refused: deletion blast radius",
        extra={"deletions": count, "existing": existing, "share": share},
    )
    raise MassDeletionRefused(
        f"refusing a mass retirement: {tripped}.\n"
        f"  Objects at stake: {_render_uids(doomed)}\n"
        "  Nothing has been changed. If this is genuinely intended, re-run with "
        f"`--allow-deletions {count}` to assert the exact count; if it is not, the store "
        "you are reconciling is probably not anchored to the projection you think it is.",
        doomed=doomed, existing=existing,
    )


def _render_uids(uids: List[str], limit: int = 10) -> str:
    """The first ``limit`` uids, with an honest count of what was elided."""
    shown = ", ".join(sorted(uids)[:limit])
    remaining = len(uids) - limit
    return f"{shown} (+{remaining} more)" if remaining > 0 else shown


def _replace_public_state(
    store: StateStore, projection_dir: Path, *, allow_deletions: Optional[int] = None
) -> None:
    """Apply the incoming projection to the public half — retaining what it does not mention.

    **This no longer deletes on absence, and that is a deliberate weakening of I3.**

    The old rule was "drop every work item the incoming projection does not carry", resting
    on: hydrate replaces the public half rather than merging into it, so an object the
    projection dropped would otherwise linger forever and ``store == hydrate(projection)``
    would stop being true. The reasoning is sound *only while the projection at HEAD is
    known to be complete*, and nothing anywhere established that. A gitignored projection,
    a shallow clone, an older branch, a Control Root resolved one directory off — each
    yields a projection that is missing objects while asserting nothing whatever about
    them. On 2026-07-20 that inference deleted ~588 work_items in one silent operation.

    So absence now means what it actually means: **no information**. The object is retained,
    untouched. Retirement must be *said*, in a committed tombstone carrying provenance
    (:data:`~atdd.state.projection.REQUIRED_TOMBSTONE_FIELDS`), and even then it is a
    record rather than a removal — physical deletion belongs to
    :func:`~atdd.state.tombstone.compact_archive` alone.

    What I3's left half now holds is the weaker, true statement: the projection is
    authoritative for every object it *mentions*. It was never authoritative about the
    objects it does not, and the code no longer pretends otherwise.

    The blast-radius guard still runs — over the set this projection *retires*, not the set
    it omits. A projection that retires an implausible share of the store in one reconcile
    is refused whether or not each individual tombstone is well-formed: saying it explicitly
    is not the same as meaning it at that scale.
    """
    from atdd.state.projection import (  # local: keeps the surface small
        MissingProjectionError,
        read_projection,
    )

    existing = store.objects.list(kind=WORK_ITEM_KIND)

    # Read the incoming projection *after* the store, so a refusal can name what is at
    # stake. Which refusal an absent projection deserves depends on that: with nothing in
    # the store it is a plain misconfiguration, and with work in it, it is the incident.
    try:
        incoming = read_projection(projection_dir, require=True)
    except MissingProjectionError as absent:
        if not existing:
            raise
        doomed = [obj.uid for obj in existing]
        raise MassDeletionRefused(
            f"refusing to empty a populated store: there is no projection directory at "
            f"{projection_dir}, and the store holds {len(existing)} work_item(s).\n"
            f"  Objects at stake: {_render_uids(doomed)}\n"
            "  An absent projection is not an assertion that the store should be empty — "
            "it is the absence of any assertion at all, and the two must never be "
            "confused. This is the shape of the 2026-07-20 mass-deletion: a gitignored, "
            "never-committed projection reading as empty at every HEAD.\n"
            "  Nothing has been changed. Check that the Control Root is the one you meant "
            "and that `.atdd/state/projection/` is committed at HEAD.",
            doomed=doomed, existing=len(existing),
        ) from absent

    if not incoming and existing:
        raise MassDeletionRefused(
            f"refusing to act on an empty projection: it carries no objects at all, but "
            f"the store holds {len(existing)} work_item(s).\n"
            f"  Objects at stake: {_render_uids([o.uid for o in existing])}\n"
            "  An empty projection is far more often a missing or uncommitted one than a "
            "genuine mass retirement, and the cost of being wrong is the whole store. "
            "Nothing has been changed.",
            doomed=[o.uid for o in existing], existing=len(existing),
        )

    # The set this projection RETIRES — objects it explicitly tombstones that the store
    # still holds as live. Not the set it omits: omission is not an instruction.
    retiring = sorted(
        obj.uid for obj in existing
        if obj.data.get("state") != STATE_TOMBSTONED
        and (incoming.get(obj.uid) or {}).get("state") == STATE_TOMBSTONED
    )
    guard_deletions(retiring, existing=len(existing), allow_deletions=allow_deletions)


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
    allow_deletions: Optional[int] = None,
) -> ReconcileResult:
    """Reconcile the local store with the projection at ``head`` (CORE-013).

    Raises :class:`StoreBaseCommitError` when the store is not anchored (P001),
    :class:`ReplayConflictError` when the overlay will not replay (R002),
    :class:`MassDeletionRefused` when the incoming projection would remove more store
    state than any guard will allow, and
    :class:`~atdd.state.projection.MissingProjectionError` when there is no projection to
    reconcile against at all (#1580). In every case the store is left exactly as it was.
    """
    control_root = Path(control_root)
    assert_reconcilable(control_root)  # a store with no HEAD of its own borrows none (#1580)
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
            allow_deletions=allow_deletions,
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
            allow_deletions=allow_deletions,
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
    allow_deletions: Optional[int] = None,
) -> ReconcileResult:
    """store := hydrate(incoming) + replay(overlay), on a copy, atomically (R001)."""
    incoming = _incoming_documents(projection_dir)
    scratch = _scratch_copy(db_path, workdir)
    conn = connect(scratch)
    try:
        store = StateStore(conn)

        # public := hydrate(incoming), subject to the deletion guards — an incoming
        # projection that is absent, empty, or implausibly smaller than the store is
        # refused here rather than applied (#1580).
        _replace_public_state(store, projection_dir, allow_deletions=allow_deletions)
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
