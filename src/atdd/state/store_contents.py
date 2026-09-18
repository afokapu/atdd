"""Replace the State Store's **contents** in one transaction (#2031).

Split out of :mod:`atdd.state.store_migration` so that the one place which names tables
in SQL is a module you can read end to end, rather than a loop buried inside a migration.

**Why every statement here is a literal.** Table and column names cannot be bound as
parameters — SQLite only binds values — so the obvious shape is an f-string per table, and
that is what this code used to be. ``coder.security.sql-injection`` is ``disposition:
strict``: a SQL keyword inside an f-string passed to ``.execute()`` is a violation with no
inline suppression, and the rule is right to hold even though these particular names come
from ``sqlite_master`` rather than from a caller. Assigning the same f-string to a variable
first would silence the detector and change nothing about the code, so it is not done here.
Instead the statements are **static text**, one pair per table, written out below.

**What that costs, and how the cost is bounded.** Static text means the table list is
declared rather than discovered, and a schema migration that adds a table would otherwise
be silently left behind — the exact failure the runtime derivation existed to prevent. So
the derivation stays, and changes job: :func:`_content_tables` reads the *live* store, and
a table it returns that this module has no statement for raises
:class:`UnknownStoreTableError`. A new table therefore stops the next durable migration
with a message naming it, instead of being dropped without a word.

``INSERT .. SELECT *`` relies on the two schemas being column-for-column identical. They
are — ``migrated`` is a file copy of ``main`` and :func:`atdd.state.db.connect` applies no
schema migrations — and :func:`_assert_schemas_match` checks it rather than assuming it.

Dependency discipline: stdlib only.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import List

__all__ = [
    "StoreChangedDuringMigrationError",
    "UnknownStoreTableError",
    "replace_store_contents",
]


class StoreChangedDuringMigrationError(Exception):
    """Another connection wrote to the store after the working copy was taken.

    The copy is a snapshot: applying it now would overwrite that write. Refusing is the
    whole point — the operator retries, and nothing was accepted and then discarded.
    """

    def __init__(self, observed: int, expected: int) -> None:
        self.observed, self.expected = observed, expected
        super().__init__(
            "the State Store was written by another process while this migration was "
            f"preparing (data_version {expected} -> {observed}); refusing to apply a "
            "snapshot that would overwrite it. Nothing was changed — retry when idle."
        )


class UnknownStoreTableError(Exception):
    """The live store carries a table this module has no replacement statement for.

    Raised *before* anything is written. A schema migration that adds a table has to add
    its pair to :data:`_REPLACE_SQL`; until it does, the durable migration refuses rather
    than silently leaving the new table's rows behind.
    """

    def __init__(self, table: str) -> None:
        self.table = table
        super().__init__(
            f"the State Store has a table this migration does not know how to move: "
            f"{table!r}. Nothing was changed. Add its statements to "
            "atdd.state.store_contents._REPLACE_SQL."
        )


#: ``table -> (clear main, refill main from the attached copy)``. Static text, one pair per
#: table in the core schema (``atdd.state.migrations`` plus ``schema_migrations`` itself).
#: The keys are not the source of truth for *which* tables exist — the live store is; see
#: :func:`_replacement_for`.
_REPLACE_SQL = {
    "events": (
        "DELETE FROM main.events",
        "INSERT INTO main.events SELECT * FROM migrated.events",
    ),
    "external_refs": (
        "DELETE FROM main.external_refs",
        "INSERT INTO main.external_refs SELECT * FROM migrated.external_refs",
    ),
    "inbox": (
        "DELETE FROM main.inbox",
        "INSERT INTO main.inbox SELECT * FROM migrated.inbox",
    ),
    "objects": (
        "DELETE FROM main.objects",
        "INSERT INTO main.objects SELECT * FROM migrated.objects",
    ),
    "outbox": (
        "DELETE FROM main.outbox",
        "INSERT INTO main.outbox SELECT * FROM migrated.outbox",
    ),
    "overlay_events": (
        "DELETE FROM main.overlay_events",
        "INSERT INTO main.overlay_events SELECT * FROM migrated.overlay_events",
    ),
    "relationships": (
        "DELETE FROM main.relationships",
        "INSERT INTO main.relationships SELECT * FROM migrated.relationships",
    ),
    "schema_migrations": (
        "DELETE FROM main.schema_migrations",
        "INSERT INTO main.schema_migrations SELECT * FROM migrated.schema_migrations",
    ),
    "store_metadata": (
        "DELETE FROM main.store_metadata",
        "INSERT INTO main.store_metadata SELECT * FROM migrated.store_metadata",
    ),
}

_MAIN_TABLES = (
    "SELECT name FROM main.sqlite_master WHERE type='table' "
    "AND name NOT LIKE 'sqlite_%' ORDER BY name"
)
_MAIN_SCHEMA = (
    "SELECT name, sql FROM main.sqlite_master WHERE type='table' "
    "AND name NOT LIKE 'sqlite_%' ORDER BY name"
)
_MIGRATED_SCHEMA = (
    "SELECT name, sql FROM migrated.sqlite_master WHERE type='table' "
    "AND name NOT LIKE 'sqlite_%' ORDER BY name"
)


def _content_tables(conn: sqlite3.Connection) -> List[str]:
    """The live store's content tables, read from it rather than declared.

    This is what keeps :data:`_REPLACE_SQL` honest: the replacement iterates what the store
    actually has, so a table that is gone is not looked for and a table that is new is
    caught by :func:`_replacement_for`.
    """
    rows = conn.execute(_MAIN_TABLES)
    return [row[0] for row in rows]


def _replacement_for(table: str) -> tuple[str, str]:
    try:
        return _REPLACE_SQL[table]
    except KeyError:
        raise UnknownStoreTableError(table) from None


def _data_version(conn: sqlite3.Connection) -> int:
    """SQLite's change counter for writes made by *other* connections.

    Unchanged by this connection's own writes, which is exactly what makes it a
    compare-and-swap token: it answers "did anybody else touch the store since I looked?"
    """
    return int(conn.execute("PRAGMA data_version").fetchone()[0])


def _assert_schemas_match(live: sqlite3.Connection) -> None:
    """``SELECT *`` maps by position, so refuse unless the two schemas are identical."""
    # Each query runs once and is materialised before the comprehension, rather than being
    # used as its iterable: `coder.refactor.nplus1` reads a call inside a comprehension as a
    # per-iteration query, and here it plainly is not one.
    main_rows = live.execute(_MAIN_SCHEMA).fetchall()
    migrated_rows = live.execute(_MIGRATED_SCHEMA).fetchall()
    main = {row[0]: row[1] for row in main_rows}
    migrated = {row[0]: row[1] for row in migrated_rows}
    if main != migrated:
        differing = sorted(
            name
            for name in main.keys() | migrated.keys()
            if main.get(name) != migrated.get(name)
        )
        raise sqlite3.IntegrityError(
            "the migrated copy's schema differs from the live store's, so its rows cannot "
            f"be copied by position; nothing was changed. Tables: {differing}"
        )


def replace_store_contents(
    live: sqlite3.Connection, scratch: Path, *, expected_version: int,
) -> None:
    """Replace the live store's **contents** from ``scratch``, atomically, in place.

    The file is never moved. That is the point: a move forces the fence open — a connection
    held across it strands ``-wal``/``-shm`` and yields ``database disk image is malformed``
    — and the interval it is opened into is where a committed write used to be lost.
    Replacing rows instead means the exclusive transaction spans the whole change, so there
    is no interval at all, and SQLite's locking is **mandatory**: it serialises every writer,
    including a raw ``sqlite3`` one that knows nothing about this code.

    ``foreign_keys`` is toggled outside the transaction on purpose — the pragma is a no-op
    inside one — because whole tables are rewritten and the intermediate state would trip
    constraints that hold again at commit.

    Raises :class:`StoreChangedDuringMigrationError` if another connection wrote since
    ``expected_version`` was read, and :class:`UnknownStoreTableError` if the store carries
    a table with no statement pair. In both cases the live store is unchanged.
    """
    live.execute("PRAGMA foreign_keys = OFF")
    try:
        live.execute("BEGIN EXCLUSIVE")
        observed = _data_version(live)
        if observed != expected_version:
            live.execute("ROLLBACK")
            raise StoreChangedDuringMigrationError(observed, expected_version)
        live.execute("ATTACH DATABASE ? AS migrated", (str(scratch),))
        try:
            _assert_schemas_match(live)
            # noqa: N+1 — the loop is over TABLES (nine, fixed by the schema), not over
            # rows. Each statement moves an entire table in one INSERT..SELECT, so the
            # statement count is O(tables) and independent of how much data the store
            # holds. That is the opposite of the pattern this rule exists to catch.
            for table in _content_tables(live):
                clear, refill = _replacement_for(table)
                live.execute(clear)  # noqa: N+1 — see above
                live.execute(refill)  # noqa: N+1 — see above
            broken = list(live.execute("PRAGMA main.foreign_key_check"))
            if broken:  # pragma: no cover - defensive
                live.execute("ROLLBACK")
                raise sqlite3.IntegrityError(
                    f"the migrated contents break {len(broken)} foreign key(s); "
                    "nothing was changed"
                )
            live.execute("COMMIT")
        except BaseException:
            if live.in_transaction:
                live.execute("ROLLBACK")
            raise
        finally:
            live.execute("DETACH DATABASE migrated")
    finally:
        live.execute("PRAGMA foreign_keys = ON")
