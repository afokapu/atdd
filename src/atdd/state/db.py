"""ATDD State Store connection + migration runner (#1168 Phase 2, #1181).

Owns the SQLite connection contract and the ordered-migration runner. Phase 2
delivers the schema and ``atdd state init`` only — typed storage APIs over these
tables are Phase 3 (#1182).

Connection contract (#1168 `atdd state init`):

- ``PRAGMA foreign_keys = ON``   — relationships/events/external_refs cascade.
- ``PRAGMA journal_mode = WAL``  — concurrent readers + a writer (sibling worktrees).
- ``PRAGMA busy_timeout = 5000`` — wait rather than fail on a transient lock.

Dependency discipline: stdlib only (``sqlite3``, ``logging``, ``pathlib``).
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import List, Optional

from atdd.state.migrations import CORE_MIGRATIONS, Migration
from atdd.state.paths import STATE_STORE_RELATIVE, resolve_control_root

_log = logging.getLogger(__name__)

_SCHEMA_MIGRATIONS_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    """Open a State Store connection with the canonical pragmas applied.

    The parent directory must already exist (``init_state_store`` creates it).
    Rows are returned as :class:`sqlite3.Row` for name-based access.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    # Canonical State Store pragmas (#1168). Set explicitly (not in a loop) so the
    # connection contract is greppable and obvious.
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def _applied_versions(conn: sqlite3.Connection) -> set[int]:
    conn.execute(_SCHEMA_MIGRATIONS_DDL)
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {int(r["version"]) for r in rows}


def apply_migrations(
    conn: sqlite3.Connection,
    migrations: Optional[List[Migration]] = None,
) -> List[int]:
    """Apply every migration whose version is not yet recorded, in order.

    Returns the list of versions newly applied (empty if already current). Each
    migration runs in its own transaction together with its ``schema_migrations``
    bookkeeping row, so a failure leaves the store at the last good version.
    """
    migrations = CORE_MIGRATIONS if migrations is None else migrations
    applied = _applied_versions(conn)
    newly: List[int] = []
    for migration in sorted(migrations, key=lambda m: m.version):
        if migration.version in applied:
            continue
        try:
            with conn:  # transaction: commit on success, rollback on exception
                # noqa: N+1 — a migration runner is inherently one statement set per
                # pending migration; this is schema setup, not a per-row query loop.
                conn.executescript(migration.sql)  # noqa: N+1
                conn.execute(  # noqa: N+1
                    "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
                    (migration.version, migration.name),
                )
        except sqlite3.Error:
            _log.error(
                "state store migration failed",
                extra={"version": migration.version, "name": migration.name},
            )
            raise
        newly.append(migration.version)
        _log.info(
            "state store migration applied",
            extra={"version": migration.version, "name": migration.name},
        )
    return newly


def current_version(conn: sqlite3.Connection) -> int:
    """Highest applied migration version (0 if none)."""
    applied = _applied_versions(conn)
    return max(applied, default=0)


def init_state_store(
    start: Optional[Path] = None,
    *,
    db_path: Optional[Path] = None,
) -> Path:
    """Create (if needed) and migrate the State Store; return its path.

    Idempotent: re-running applies only pending migrations. ``db_path`` overrides
    location for tests; otherwise the path is resolved from the Control Root of
    ``start`` (default: cwd) via the #1177 resolver.
    """
    if db_path is None:
        start_path = Path(start) if start is not None else Path.cwd()
        resolution = resolve_control_root(start_path)
        db_path = resolution.control_root / STATE_STORE_RELATIVE
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = connect(db_path)
    try:
        apply_migrations(conn)
    finally:
        conn.close()
    return db_path
