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


#: Seed version for the singleton ``release`` object (#1172). This is the value
#: current on ``main`` when migration v2 was authored; it is a *baseline*, not a
#: live value — subsequent bumps update ``data.version`` and append
#: ``version_bumped`` events (see :mod:`atdd.state.version`). A fresh store starts
#: here; a build over a never-bumped store therefore reports this version.
RELEASE_SEED_VERSION = "3.149.0"

#: #1172 — register the singleton ``release`` object that owns the source-of-truth
#: version. Reuses the existing ``objects`` table (NO new table); the ``release``
#: kind is just a value in ``objects.kind``. ``ON CONFLICT(uid) DO NOTHING`` keeps
#: an already-present/imported release object intact (idempotent re-seed).
_RELEASE_KIND_SQL = f"""
INSERT INTO objects (uid, kind, state, data)
VALUES ('release', 'release', NULL, '{{"version": "{RELEASE_SEED_VERSION}"}}')
ON CONFLICT(uid) DO NOTHING;
"""


#: #1400 reconcile-local-store — the two tables the reconcile spine needs (spec §3).
#:
#: ``overlay_events`` makes local overlay EXPLICIT. The store is the private
#: authoring workspace; every authoring command that has not yet been committed
#: into the projection appends one typed, replayable event here. Overlay is never
#: *inferred* by diffing SQLite against a hydrated baseline — SQLite holds derived
#: data, indexes and transient fields, so a diff cannot recover user intent.
#:
#: ``store_metadata`` records ``store_base_commit``: the commit the store was last
#: hydrated from. It is what makes ``store = hydrate(projection @ base) +
#: replay(overlay)`` (I3) resolvable without guessing.
_OVERLAY_TABLES_SQL = """
CREATE TABLE overlay_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id    TEXT NOT NULL UNIQUE,         -- stable across reconciles; never reminted
    seq         INTEGER NOT NULL,             -- append order == replay order
    object_uid  TEXT NOT NULL,                -- no FK: an event outlives its object (audit)
    kind        TEXT NOT NULL,                -- one of the seven authoring kinds
    payload     TEXT NOT NULL DEFAULT '{}',   -- JSON; everything replay needs
    status      TEXT NOT NULL DEFAULT 'pending',
                -- pending | projected | committed | discarded | conflicted
    projection_digest TEXT,                   -- back-ref: the projection representing it
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_overlay_events_status ON overlay_events(status);
CREATE INDEX idx_overlay_events_object ON overlay_events(object_uid);

CREATE TABLE store_metadata (
    key         TEXT PRIMARY KEY,
    value       TEXT
);
"""


#: #1655 outbox disposition — the columns that let a row LEAVE the queue without
#: being sent and without being deleted.
#:
#: Before this, ``outbox.status`` was ``pending | sent | failed`` with no fourth
#: option, so an undeliverable row had exactly two futures: sit pending forever, or
#: be ``DELETE``d. The first is what produced the stranded backlog #1655 triaged;
#: the second destroys the audit trail of a decision the store once made. Neither is
#: acceptable for a queue whose rows are *decisions* (a version to publish, an issue
#: to file).
#:
#: ``discarded`` is that fourth status, and ``disposition`` makes it answerable: a
#: row may only be discarded against a recorded, non-empty reason (enforced in
#: :meth:`atdd.state.store.SyncStore.discard`, not by the schema — SQLite cannot
#: express "non-empty when status='discarded'" without a table rewrite). The row
#: itself is preserved, so "why is this not in GitHub?" stays answerable forever.
#:
#: ``ALTER TABLE ... ADD COLUMN`` is the whole migration: no table rewrite, no data
#: copy, and every existing row keeps its status with NULL disposition.
_OUTBOX_DISPOSITION_SQL = """
ALTER TABLE outbox ADD COLUMN disposition TEXT;
ALTER TABLE outbox ADD COLUMN disposed_at  TEXT;
"""


#: Ordered, append-only core migrations. NEVER edit an applied migration in place
#: — add a new one with the next version number.
CORE_MIGRATIONS: List[Migration] = [
    Migration(version=1, name="core_tables", sql=_CORE_TABLES_SQL),
    Migration(version=2, name="release_kind", sql=_RELEASE_KIND_SQL),
    Migration(version=3, name="overlay_and_metadata", sql=_OVERLAY_TABLES_SQL),
    Migration(version=4, name="outbox_disposition", sql=_OUTBOX_DISPOSITION_SQL),
]


def latest_version(migrations: List[Migration] = CORE_MIGRATIONS) -> int:
    """Highest migration version defined (0 if none)."""
    return max((m.version for m in migrations), default=0)
