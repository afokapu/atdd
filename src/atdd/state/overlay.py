"""The explicit overlay event log (#1400 CORE-011, spec §3).

The correction this module exists to make: **local overlay is recorded, never
inferred**. SQLite holds derived data, caches, indexes, migration bookkeeping and
transient fields, so diffing it against a hydrated baseline cannot recover *user
intent* — it recovers byte churn. Instead, every local authoring command that has
not yet been committed into the projection appends one typed, replayable event
here, in the same transaction as the object write it describes.

That gives reconcile something exact to replay:

    store == hydrate(projection @ store_base_commit) + replay(local_overlay)

Two guarantees make it trustworthy.

**Nothing writes an object without saying why (E001).** Inside an
:func:`authoring_session` a SQLite trigger refuses any ``objects`` write that is
not covered by an overlay event, aborting the transaction and leaving the table
untouched. The sanctioned path — :func:`author` — appends the event and applies it
atomically, so the two can never drift apart.

**Nothing is replayed twice (Y001).** Each event carries a stable ``event_id``
minted once and never re-minted, and a status:

    pending  → appended locally, not yet in any projection
    projected→ written into a projection file (which digest is recorded)
    committed→ that projection reached the shared truth; replay is DONE with it
    discarded→ withdrawn locally
    conflicted→ replay refused it; it is kept for the operator, never re-applied

Only ``pending`` and ``projected`` events are replayable. A ``projected`` event is
still replayable because a projection file on disk is not yet *shared* truth — it
becomes ``committed`` only when the incoming projection at HEAD already reflects
it, which :mod:`atdd.state.reconcile` detects and records.

Dependency discipline: stdlib + ``atdd.state`` only. No provider is imported,
discovered or consulted anywhere on this path (I7).
"""
from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence

from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.projection import STATE_ACTIVE, STATE_TOMBSTONED

_log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# The taxonomy (spec §3) — the seven authoring commands, and nothing else
# --------------------------------------------------------------------------- #
OBJECT_CREATED = "object_created"
BODY_UPDATED = "body_updated"
PHASE_TRANSITION_REQUESTED = "phase_transition_requested"
TRAIN_UPDATED = "train_updated"
WMBT_ADDED = "wmbt_added"
TOMBSTONE_REQUESTED = "tombstone_requested"
EXTERNAL_REF_APPLIED = "external_ref_applied"

#: Every authoring command that may append an overlay event. A kind outside this
#: table is a programming error, not a new feature — it would be replayed by
#: nothing and understood by no one.
EVENT_KINDS = (
    OBJECT_CREATED,
    BODY_UPDATED,
    PHASE_TRANSITION_REQUESTED,
    TRAIN_UPDATED,
    WMBT_ADDED,
    TOMBSTONE_REQUESTED,
    EXTERNAL_REF_APPLIED,
)

STATUS_PENDING = "pending"
STATUS_PROJECTED = "projected"
STATUS_COMMITTED = "committed"
STATUS_DISCARDED = "discarded"
STATUS_CONFLICTED = "conflicted"

STATUSES = (
    STATUS_PENDING,
    STATUS_PROJECTED,
    STATUS_COMMITTED,
    STATUS_DISCARDED,
    STATUS_CONFLICTED,
)

#: The statuses reconcile replays. ``committed`` is done (the shared truth already
#: carries it), ``discarded`` was withdrawn, ``conflicted`` was refused — replaying
#: any of the three would apply the same intent twice (Y001).
REPLAYABLE_STATUSES = (STATUS_PENDING, STATUS_PROJECTED)

#: The uid namespace for an overlay event. Local-only: it never reaches a
#: projection file, so it is not bound by the projection's determinism guard.
EVENT_ID_PREFIX = "ev_"

#: The sentinel the guard trigger raises with, so a SQLite ``IntegrityError`` from
#: *our* trigger is distinguishable from a genuine constraint violation.
_GUARD_SENTINEL = "atdd-overlay: unlogged object write"


class OverlayLogError(RuntimeError):
    """An ``objects`` write was attempted without an overlay event to explain it.

    Carries the offending ``object_uid``. The transaction is already rolled back by
    the time this surfaces: the guard is a ``BEFORE`` trigger, so the write never
    reached the table.
    """

    def __init__(self, message: str, *, object_uid: Optional[str] = None) -> None:
        self.object_uid = object_uid
        super().__init__(message)


@dataclass(frozen=True)
class OverlayEvent:
    """One typed, replayable local authoring event."""

    event_id: str
    seq: int
    object_uid: str
    kind: str
    payload: Dict[str, Any] = field(default_factory=dict)
    status: str = STATUS_PENDING
    projection_digest: Optional[str] = None

    @staticmethod
    def _from_row(row: sqlite3.Row) -> "OverlayEvent":
        return OverlayEvent(
            event_id=row["event_id"],
            seq=int(row["seq"]),
            object_uid=row["object_uid"],
            kind=row["kind"],
            payload=json.loads(row["payload"] or "{}"),
            status=row["status"],
            projection_digest=row["projection_digest"],
        )


def mint_event_id() -> str:
    """Mint a stable event id. Minted once at append and never re-minted (Y001)."""
    return EVENT_ID_PREFIX + uuid.uuid4().hex


# --------------------------------------------------------------------------- #
# Reading the log
# --------------------------------------------------------------------------- #
def _rows(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> List[OverlayEvent]:
    # One query, then a pure mapping over its rows — never a query per row.
    fetched = conn.execute(sql, tuple(params)).fetchall()
    return [OverlayEvent._from_row(row) for row in fetched]


def all_events(conn: sqlite3.Connection) -> List[OverlayEvent]:
    """Every overlay event ever appended, in append order — the local audit trail."""
    return _rows(conn, "SELECT * FROM overlay_events ORDER BY seq")


def events_for(conn: sqlite3.Connection, object_uid: str) -> List[OverlayEvent]:
    """Every event touching ``object_uid``, in append order."""
    return _rows(
        conn, "SELECT * FROM overlay_events WHERE object_uid=? ORDER BY seq", (object_uid,)
    )


def replayable_events(conn: sqlite3.Connection) -> List[OverlayEvent]:
    """The overlay reconcile must replay: ``pending`` and ``projected``, in order (Y001).

    Append order *is* replay order: a create followed by a transition means nothing
    if replayed the other way round.
    """
    placeholders = ",".join("?" for _ in REPLAYABLE_STATUSES)
    return _rows(
        conn,
        f"SELECT * FROM overlay_events WHERE status IN ({placeholders}) ORDER BY seq",
        REPLAYABLE_STATUSES,
    )


def is_dirty(conn: sqlite3.Connection) -> bool:
    """True when the store carries uncommitted overlay — the authority on dirtiness.

    Read from the events themselves, never from the ``store_metadata`` dirty marker:
    a stale marker must never be able to lose a developer's local work (I5).
    """
    return bool(replayable_events(conn))


def set_status(
    conn: sqlite3.Connection,
    event_ids: Iterable[str],
    status: str,
    *,
    projection_digest: Optional[str] = None,
) -> int:
    """Move ``event_ids`` to ``status``; return how many rows moved.

    ``projection_digest`` is the back-reference recorded when events are projected:
    it names *which* projection represents them, which is what lets reconcile tell a
    replayed event from a re-replayed one (Y001).
    """
    if status not in STATUSES:
        raise ValueError(f"unknown overlay event status {status!r} (expected one of {STATUSES})")
    ids = list(event_ids)
    if not ids:
        return 0
    with conn:
        cur = conn.executemany(
            "UPDATE overlay_events SET status=?, projection_digest=COALESCE(?, projection_digest) "
            "WHERE event_id=?",
            [(status, projection_digest, event_id) for event_id in ids],
        )
    _log.info(
        "overlay events moved", extra={"status": status, "events": len(ids)},
    )
    return cur.rowcount


def mark_projected(conn: sqlite3.Connection, digest: str) -> int:
    """Record that the projection at ``digest`` represents every pending event (Y001).

    Projecting is not committing: the events stay *replayable* until the shared
    truth at HEAD actually carries them. What changes is that the projection now has
    a name, so reconcile can recognise its own work coming back.
    """
    pending = [e.event_id for e in replayable_events(conn) if e.status == STATUS_PENDING]
    return set_status(conn, pending, STATUS_PROJECTED, projection_digest=digest)


# --------------------------------------------------------------------------- #
# Applying an event to a store — the ONE function authoring and replay share
# --------------------------------------------------------------------------- #
#: The ticket table the guard trigger consults. Created on demand, because
#: :func:`apply_event` also runs during *replay* — outside any authoring session, where
#: no guard is installed — and must present a ticket there too rather than crash.
_TICKET_DDL = "CREATE TEMP TABLE IF NOT EXISTS _atdd_overlay_ticket (uid TEXT PRIMARY KEY)"


def _write_object(
    conn: sqlite3.Connection, uid: str, *, state: Optional[str], data: Dict[str, Any]
) -> None:
    """Write a work item, presenting the guard the ticket that says an event covers it.

    The ticket is issued for this one write and withdrawn immediately after, so a
    *second*, unlogged write to the same uid in the same session is still refused.
    """
    conn.execute(_TICKET_DDL)
    conn.execute("INSERT OR REPLACE INTO temp._atdd_overlay_ticket (uid) VALUES (?)", (uid,))
    conn.execute(
        """
        INSERT INTO objects (uid, kind, state, data) VALUES (?, ?, ?, ?)
        ON CONFLICT(uid) DO UPDATE SET
            kind=excluded.kind, state=excluded.state, data=excluded.data,
            updated_at=datetime('now')
        """,
        (uid, WORK_ITEM_KIND, state, json.dumps(data, sort_keys=True)),
    )
    conn.execute("DELETE FROM temp._atdd_overlay_ticket WHERE uid=?", (uid,))


def _current(conn: sqlite3.Connection, uid: str) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT state, data FROM objects WHERE uid=?", (uid,)).fetchone()
    if row is None:
        return None
    data = json.loads(row["data"] or "{}")
    data["phase"] = row["state"]
    return data


def apply_event(conn: sqlite3.Connection, event: OverlayEvent) -> None:
    """Apply one overlay event to ``conn``'s object store.

    This is the single definition of what an authoring command *means*, and both
    callers go through it: the local command that appends the event, and the replay
    that re-applies it onto a freshly hydrated incoming projection. They cannot
    drift, because there is only one implementation of the semantics.
    """
    state = project_event(_current(conn, event.object_uid), event)
    phase = state.pop("phase", None)
    _write_object(conn, event.object_uid, state=phase, data=state)


def project_event(
    current: Optional[Dict[str, Any]], event: OverlayEvent
) -> Dict[str, Any]:
    """The object state an event produces from ``current`` — pure, no I/O.

    Kept pure so reconcile can ask "would this event change anything?" without
    touching a store: an event whose output equals the incoming state is one the
    shared truth already carries, and replaying it would be the double-apply Y001
    exists to prevent.
    """
    payload = event.payload
    data: Dict[str, Any] = dict(current or {})

    if event.kind == OBJECT_CREATED:
        data.update(payload.get("data", {}))
        data.setdefault("state", STATE_ACTIVE)
        data["phase"] = payload.get("phase", data.get("phase"))
    elif event.kind == BODY_UPDATED:
        data["body"] = payload["body"]
    elif event.kind == PHASE_TRANSITION_REQUESTED:
        data["phase"] = payload["to_phase"]
    elif event.kind == TRAIN_UPDATED:
        data["train"] = payload["train"]
    elif event.kind == WMBT_ADDED:
        wmbts = list(data.get("wmbts") or [])
        for wmbt in payload["wmbts"] if "wmbts" in payload else [payload["wmbt"]]:
            if wmbt not in wmbts:
                wmbts.append(wmbt)
        data["wmbts"] = sorted(wmbts)
    elif event.kind == TOMBSTONE_REQUESTED:
        data["state"] = STATE_TOMBSTONED
        data["tombstone"] = dict(payload.get("tombstone", {"reason": payload.get("reason", "")}))
    elif event.kind == EXTERNAL_REF_APPLIED:
        refs = dict(data.get("external_refs") or {})
        refs[payload["provider"]] = payload["ref"]
        data["external_refs"] = refs
    else:
        raise ValueError(f"unknown overlay event kind {event.kind!r} (expected one of {EVENT_KINDS})")

    return data


# --------------------------------------------------------------------------- #
# The guard (E001-UNIT-002) — no object write without an event to explain it
# --------------------------------------------------------------------------- #
#: A TEMP trigger, so it guards *authoring* only. ``hydrate`` and ``replay`` write
#: public state — state that already exists in the shared truth or in the log — and
#: are not authoring, so they run outside a session and are not guarded.
_GUARD_SQL = f"""
{_TICKET_DDL};
DELETE FROM temp._atdd_overlay_ticket;

CREATE TEMP TRIGGER _atdd_overlay_guard_insert BEFORE INSERT ON objects
WHEN NEW.kind = '{WORK_ITEM_KIND}'
 AND NOT EXISTS (SELECT 1 FROM temp._atdd_overlay_ticket WHERE uid = NEW.uid)
BEGIN
    SELECT RAISE(ABORT, '{_GUARD_SENTINEL} ' || NEW.uid);
END;

CREATE TEMP TRIGGER _atdd_overlay_guard_update BEFORE UPDATE ON objects
WHEN NEW.kind = '{WORK_ITEM_KIND}'
 AND NOT EXISTS (SELECT 1 FROM temp._atdd_overlay_ticket WHERE uid = NEW.uid)
BEGIN
    SELECT RAISE(ABORT, '{_GUARD_SENTINEL} ' || NEW.uid);
END;
"""

_GUARD_TEARDOWN_SQL = """
DROP TRIGGER IF EXISTS _atdd_overlay_guard_insert;
DROP TRIGGER IF EXISTS _atdd_overlay_guard_update;
DELETE FROM temp._atdd_overlay_ticket;
"""


def _uid_from_guard_error(exc: sqlite3.IntegrityError) -> Optional[str]:
    """The uid the guard trigger named, so the refusal can point at the object."""
    message = str(exc)
    if _GUARD_SENTINEL not in message:
        return None
    return message.split(_GUARD_SENTINEL, 1)[1].strip() or None


class AuthoringSession:
    """The sanctioned write path: an object write and its overlay event, atomically."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def author(
        self, kind: str, object_uid: str, payload: Optional[Dict[str, Any]] = None
    ) -> OverlayEvent:
        """Append one typed event and apply it — one command, one event, one transaction."""
        if kind not in EVENT_KINDS:
            raise ValueError(
                f"unknown authoring command {kind!r} (expected one of {EVENT_KINDS})"
            )
        payload = dict(payload or {})
        row = self._conn.execute("SELECT COALESCE(MAX(seq), 0) AS seq FROM overlay_events").fetchone()
        event = OverlayEvent(
            event_id=mint_event_id(),
            seq=int(row["seq"]) + 1,
            object_uid=object_uid,
            kind=kind,
            payload=payload,
        )
        self._conn.execute(
            "INSERT INTO overlay_events (event_id, seq, object_uid, kind, payload, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                event.event_id, event.seq, event.object_uid, event.kind,
                json.dumps(event.payload, sort_keys=True), event.status,
            ),
        )
        apply_event(self._conn, event)
        return event


@contextmanager
def authoring_session(conn: sqlite3.Connection) -> Iterator[AuthoringSession]:
    """Guard every ``objects`` write inside the block with an overlay event (E001).

    The event and the object write commit or roll back **together**: one explicit
    transaction wraps both, and a trigger refuses any write the log does not cover.
    An unlogged write therefore raises :class:`OverlayLogError` naming the uid, and
    leaves ``objects`` exactly as it was — the store cannot end up holding a change
    that reconcile has no event to replay.
    """
    conn.commit()  # close any implicit transaction so the guard owns a clean one
    conn.executescript(_GUARD_SQL)
    conn.execute("BEGIN")
    try:
        yield AuthoringSession(conn)
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        uid = _uid_from_guard_error(exc)
        if uid is None:
            raise
        _log.warning("overlay refused an unlogged object write", extra={"uid": uid})
        raise OverlayLogError(
            f"refusing an object write with no overlay event to explain it: {uid}. "
            "Every local authoring command must append a typed overlay event in the "
            "same transaction — overlay is recorded, never inferred from a SQLite diff.",
            object_uid=uid,
        ) from exc
    except BaseException:
        conn.rollback()
        raise
    else:
        conn.commit()
    finally:
        conn.executescript(_GUARD_TEARDOWN_SQL)


def author(
    conn: sqlite3.Connection,
    kind: str,
    object_uid: str,
    payload: Optional[Dict[str, Any]] = None,
) -> OverlayEvent:
    """Run one authoring command: append its overlay event and apply it, atomically."""
    with authoring_session(conn) as session:
        return session.author(kind, object_uid, payload)
