"""ATDD State Store schema migrations (#1168 Phase 2, #1181).

Migrations are ordered, append-only, and embedded as Python-held SQL (rather
than loose ``.sql`` files) so they ship in the wheel without package-data
wiring. The runner in :mod:`atdd.state.db` applies any migration whose
``version`` is greater than the highest recorded in ``schema_migrations``.

Migration 0001 creates the core extensible primitives from #1168's Data Model —
``objects``, ``relationships``, ``events``, ``external_refs``, ``inbox``,
``outbox`` — NOT a Hub- or GitHub-specific schema. Hub- and provider-owned
object kinds/projections are layered on later (Phases 4-6) without new core
tables.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str


_CORE_TABLES_SQL = """
CREATE TABLE objects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    uid         TEXT NOT NULL UNIQUE,         -- stable local identity (slug / generated id)
    kind        TEXT NOT NULL,                -- work_item | run | evidence | hub_session | ...
    state       TEXT,                         -- coarse lifecycle state (e.g. phase/status)
    data        TEXT NOT NULL DEFAULT '{}',   -- JSON attribute bag
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_objects_kind ON objects(kind);

CREATE TABLE relationships (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    src_uid     TEXT NOT NULL,
    dst_uid     TEXT NOT NULL,
    rel_type    TEXT NOT NULL,                -- parent_of | owns_worktree | mirrors | ...
    data        TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (src_uid) REFERENCES objects(uid) ON DELETE CASCADE,
    FOREIGN KEY (dst_uid) REFERENCES objects(uid) ON DELETE CASCADE,
    UNIQUE (src_uid, dst_uid, rel_type)
);
CREATE INDEX idx_relationships_src ON relationships(src_uid);
CREATE INDEX idx_relationships_dst ON relationships(dst_uid);

CREATE TABLE events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    object_uid  TEXT,                         -- nullable: system-level events
    seq         INTEGER NOT NULL,             -- monotonic ordering
    event_type  TEXT NOT NULL,
    payload     TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (object_uid) REFERENCES objects(uid) ON DELETE CASCADE
);
CREATE INDEX idx_events_object ON events(object_uid);
CREATE INDEX idx_events_seq ON events(seq);

CREATE TABLE external_refs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    object_uid  TEXT NOT NULL,
    provider    TEXT NOT NULL,                -- github | jira | cmux | ...
    ref_kind    TEXT NOT NULL,                -- issue | pr | session | ...
    ref_value   TEXT NOT NULL,                -- provider-side identifier (issue number, url, ...)
    data        TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (object_uid) REFERENCES objects(uid) ON DELETE CASCADE,
    UNIQUE (provider, ref_kind, ref_value)
);
CREATE INDEX idx_external_refs_object ON external_refs(object_uid);

CREATE TABLE inbox (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    provider     TEXT NOT NULL,
    payload      TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',   -- pending | processed | failed
    received_at  TEXT NOT NULL DEFAULT (datetime('now')),
    processed_at TEXT
);
CREATE INDEX idx_inbox_status ON inbox(status);

CREATE TABLE outbox (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    provider    TEXT NOT NULL,
    operation   TEXT NOT NULL,                -- create_issue | add_label | comment | ...
    payload     TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',    -- pending | sent | failed
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    sent_at     TEXT
);
CREATE INDEX idx_outbox_status ON outbox(status);
"""


#: Ordered, append-only core migrations. NEVER edit an applied migration in place
#: — add a new one with the next version number.
CORE_MIGRATIONS: List[Migration] = [
    Migration(version=1, name="core_tables", sql=_CORE_TABLES_SQL),
]


def latest_version(migrations: List[Migration] = CORE_MIGRATIONS) -> int:
    """Highest migration version defined (0 if none)."""
    return max((m.version for m in migrations), default=0)
