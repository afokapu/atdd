"""ATDD State Store typed storage APIs (#1168 Phase 3, #1182).

Typed stores over the #1181 core tables so call sites never write raw SQL:

- :class:`ObjectStore`        — work items / runs / evidence / … (the `objects` table)
- :class:`RelationshipStore`  — typed edges between objects
- :class:`EventStore`         — the append-only event log
- :class:`ExternalRefStore`   — provider links (GitHub issue/PR, cmux session)
- :class:`SyncStore`          — the `inbox` / `outbox` sync queues

:class:`StateStore` bundles all five over one connection. Every store takes an
already-migrated :class:`sqlite3.Connection` (see :func:`atdd.state.db.connect`
/ :func:`atdd.state.db.init_state_store`); JSON ``data`` columns are
(de)serialized at this boundary so callers pass/get plain ``dict``\\ s.

Dependency discipline: stdlib only (``sqlite3``, ``json``, ``logging``).
"""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_log = logging.getLogger(__name__)


def _loads(blob: Optional[str]) -> Dict[str, Any]:
    return json.loads(blob) if blob else {}


def _dumps(data: Optional[Dict[str, Any]]) -> str:
    return json.dumps(data or {}, sort_keys=True)


# --------------------------------------------------------------------------- #
# Row dataclasses
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Object:
    uid: str
    kind: str
    state: Optional[str]
    data: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @staticmethod
    def _from_row(row: sqlite3.Row) -> "Object":
        return Object(
            uid=row["uid"], kind=row["kind"], state=row["state"],
            data=_loads(row["data"]), created_at=row["created_at"], updated_at=row["updated_at"],
        )


@dataclass(frozen=True)
class Relationship:
    src_uid: str
    dst_uid: str
    rel_type: str
    data: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def _from_row(row: sqlite3.Row) -> "Relationship":
        return Relationship(row["src_uid"], row["dst_uid"], row["rel_type"], _loads(row["data"]))


@dataclass(frozen=True)
class Event:
    id: int
    object_uid: Optional[str]
    seq: int
    event_type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[str] = None

    @staticmethod
    def _from_row(row: sqlite3.Row) -> "Event":
        return Event(
            id=row["id"], object_uid=row["object_uid"], seq=row["seq"],
            event_type=row["event_type"], payload=_loads(row["payload"]), created_at=row["created_at"],
        )


@dataclass(frozen=True)
class ExternalRef:
    object_uid: str
    provider: str
    ref_kind: str
    ref_value: str
    data: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def _from_row(row: sqlite3.Row) -> "ExternalRef":
        return ExternalRef(
            object_uid=row["object_uid"], provider=row["provider"], ref_kind=row["ref_kind"],
            ref_value=row["ref_value"], data=_loads(row["data"]),
        )


@dataclass(frozen=True)
class SyncMessage:
    id: int
    provider: str
    payload: Dict[str, Any]
    status: str
    operation: Optional[str] = None  # outbox only


@dataclass(frozen=True)
class OutboxBacklog:
    """What is waiting in the outbox, and since when (#1711/C015).

    ``pending_outbox`` returns the rows but not their age, so the figure that
    actually distinguishes a moving queue from a stalled one — the enqueue time
    of the oldest row still waiting — was reachable only by opening the SQLite
    file by hand. Thirty pending rows reads as a busy queue; thirty pending rows
    whose oldest is from 2026-07-09 reads as a queue that has not moved in 25
    days, which is the fact this defect was found through.

    ``by_provider`` is a count per provider name rather than a total, so a single
    unregistered provider is attributable instead of averaged into the rest.
    """

    pending: int
    oldest_enqueued_at: Optional[str]          # None exactly when pending == 0
    by_provider: Dict[str, int] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Stores
# --------------------------------------------------------------------------- #
class _BaseStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn


class ObjectStore(_BaseStore):
    """CRUD over ``objects`` (keyed by the stable local ``uid``)."""

    def upsert(self, uid: str, kind: str, *, state: Optional[str] = None,
               data: Optional[Dict[str, Any]] = None) -> Object:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO objects (uid, kind, state, data) VALUES (?, ?, ?, ?)
                ON CONFLICT(uid) DO UPDATE SET
                    kind=excluded.kind, state=excluded.state, data=excluded.data,
                    updated_at=datetime('now')
                """,
                (uid, kind, state, _dumps(data)),
            )
        got = self.get(uid)
        assert got is not None  # just written
        return got

    def set_state(self, uid: str, state: Optional[str]) -> None:
        with self._conn:
            cur = self._conn.execute(
                "UPDATE objects SET state=?, updated_at=datetime('now') WHERE uid=?",
                (state, uid),
            )
        if cur.rowcount == 0:
            raise KeyError(f"object not found: {uid}")

    def get(self, uid: str) -> Optional[Object]:
        row = self._conn.execute("SELECT * FROM objects WHERE uid=?", (uid,)).fetchone()
        return Object._from_row(row) if row else None

    def list(self, *, kind: Optional[str] = None) -> List[Object]:
        if kind is None:
            rows = self._conn.execute("SELECT * FROM objects ORDER BY uid").fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM objects WHERE kind=? ORDER BY uid", (kind,)
            ).fetchall()
        return [Object._from_row(r) for r in rows]

    def delete(self, uid: str) -> bool:
        with self._conn:
            cur = self._conn.execute("DELETE FROM objects WHERE uid=?", (uid,))
        return cur.rowcount > 0


class RelationshipStore(_BaseStore):
    """Typed edges between objects (FK-cascading on object delete)."""

    def add(self, src_uid: str, dst_uid: str, rel_type: str,
            *, data: Optional[Dict[str, Any]] = None) -> Relationship:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO relationships (src_uid, dst_uid, rel_type, data) VALUES (?, ?, ?, ?)
                ON CONFLICT(src_uid, dst_uid, rel_type) DO UPDATE SET data=excluded.data
                """,
                (src_uid, dst_uid, rel_type, _dumps(data)),
            )
        return Relationship(src_uid, dst_uid, rel_type, data or {})

    def list(self, *, src_uid: Optional[str] = None, dst_uid: Optional[str] = None,
             rel_type: Optional[str] = None) -> List[Relationship]:
        clauses, params = [], []
        if src_uid is not None:
            clauses.append("src_uid=?"); params.append(src_uid)
        if dst_uid is not None:
            clauses.append("dst_uid=?"); params.append(dst_uid)
        if rel_type is not None:
            clauses.append("rel_type=?"); params.append(rel_type)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = self._conn.execute(
            f"SELECT * FROM relationships{where} ORDER BY id", params
        ).fetchall()
        return [Relationship._from_row(r) for r in rows]

    def remove(self, src_uid: str, dst_uid: str, rel_type: str) -> bool:
        with self._conn:
            cur = self._conn.execute(
                "DELETE FROM relationships WHERE src_uid=? AND dst_uid=? AND rel_type=?",
                (src_uid, dst_uid, rel_type),
            )
        return cur.rowcount > 0


class EventStore(_BaseStore):
    """Append-only event log with a monotonic global ``seq``."""

    def append(self, event_type: str, *, object_uid: Optional[str] = None,
               payload: Optional[Dict[str, Any]] = None) -> Event:
        with self._conn:
            seq = self._conn.execute(
                "SELECT COALESCE(MAX(seq), 0) + 1 FROM events"
            ).fetchone()[0]
            cur = self._conn.execute(
                "INSERT INTO events (object_uid, seq, event_type, payload) VALUES (?, ?, ?, ?)",
                (object_uid, seq, event_type, _dumps(payload)),
            )
            event_id = cur.lastrowid
        row = self._conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        return Event._from_row(row)

    def list(self, *, object_uid: Optional[str] = None) -> List[Event]:
        if object_uid is None:
            rows = self._conn.execute("SELECT * FROM events ORDER BY seq").fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM events WHERE object_uid=? ORDER BY seq", (object_uid,)
            ).fetchall()
        return [Event._from_row(r) for r in rows]


class ExternalRefStore(_BaseStore):
    """Provider links — a local object's projection onto an external provider."""

    def link(self, object_uid: str, provider: str, ref_kind: str, ref_value: str,
             *, data: Optional[Dict[str, Any]] = None) -> ExternalRef:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO external_refs (object_uid, provider, ref_kind, ref_value, data)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(provider, ref_kind, ref_value) DO UPDATE SET
                    object_uid=excluded.object_uid, data=excluded.data
                """,
                (object_uid, provider, ref_kind, ref_value, _dumps(data)),
            )
        return ExternalRef(object_uid, provider, ref_kind, ref_value, data or {})

    def resolve(self, provider: str, ref_kind: str, ref_value: str) -> Optional[ExternalRef]:
        row = self._conn.execute(
            "SELECT * FROM external_refs WHERE provider=? AND ref_kind=? AND ref_value=?",
            (provider, ref_kind, ref_value),
        ).fetchone()
        return ExternalRef._from_row(row) if row else None

    def for_object(self, object_uid: str) -> List[ExternalRef]:
        rows = self._conn.execute(
            "SELECT * FROM external_refs WHERE object_uid=? ORDER BY id", (object_uid,)
        ).fetchall()
        return [ExternalRef._from_row(r) for r in rows]

    def all(self) -> List[ExternalRef]:
        """Every external ref (one query — for bulk projection grouping)."""
        rows = self._conn.execute("SELECT * FROM external_refs ORDER BY id").fetchall()
        return [ExternalRef._from_row(r) for r in rows]


class SyncStore(_BaseStore):
    """The ``inbox`` (provider→local) and ``outbox`` (local→provider) queues."""

    def enqueue_outbox(self, provider: str, operation: str,
                       payload: Dict[str, Any]) -> int:
        with self._conn:
            cur = self._conn.execute(
                "INSERT INTO outbox (provider, operation, payload) VALUES (?, ?, ?)",
                (provider, operation, _dumps(payload)),
            )
        return int(cur.lastrowid)

    def pending_outbox(self) -> List[SyncMessage]:
        rows = self._conn.execute(
            "SELECT * FROM outbox WHERE status='pending' ORDER BY id"
        ).fetchall()
        return [SyncMessage(r["id"], r["provider"], _loads(r["payload"]), r["status"], r["operation"])
                for r in rows]

    def outbox_backlog(self) -> OutboxBacklog:
        """The pending queue summarised: how many, since when, and for whom (#1711).

        One pass over the pending rows rather than three queries — the table is
        the size of the undelivered backlog, and a summary that needed its own
        round trip per figure would discourage printing it, which is how the
        figure went unprinted for 25 days in the first place.
        """
        rows = self._conn.execute(
            "SELECT provider, created_at FROM outbox WHERE status='pending'"
        ).fetchall()
        by_provider: Dict[str, int] = {}
        oldest: Optional[str] = None
        for row in rows:
            by_provider[row["provider"]] = by_provider.get(row["provider"], 0) + 1
            created = row["created_at"]
            if created is not None and (oldest is None or created < oldest):
                oldest = created
        return OutboxBacklog(
            pending=len(rows), oldest_enqueued_at=oldest, by_provider=by_provider,
        )

    def mark_sent(self, outbox_id: int) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE outbox SET status='sent', sent_at=datetime('now') WHERE id=?", (outbox_id,)
            )

    def enqueue_inbox(self, provider: str, payload: Dict[str, Any]) -> int:
        with self._conn:
            cur = self._conn.execute(
                "INSERT INTO inbox (provider, payload) VALUES (?, ?)",
                (provider, _dumps(payload)),
            )
        return int(cur.lastrowid)

    def pending_inbox(self) -> List[SyncMessage]:
        rows = self._conn.execute(
            "SELECT * FROM inbox WHERE status='pending' ORDER BY id"
        ).fetchall()
        return [SyncMessage(r["id"], r["provider"], _loads(r["payload"]), r["status"]) for r in rows]

    def mark_processed(self, inbox_id: int) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE inbox SET status='processed', processed_at=datetime('now') WHERE id=?",
                (inbox_id,),
            )


@dataclass
class StateStore:
    """Facade bundling the five typed stores over one connection."""

    conn: sqlite3.Connection

    def __post_init__(self) -> None:
        self.objects = ObjectStore(self.conn)
        self.relationships = RelationshipStore(self.conn)
        self.events = EventStore(self.conn)
        self.external_refs = ExternalRefStore(self.conn)
        self.sync = SyncStore(self.conn)
