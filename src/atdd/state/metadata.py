"""Store metadata — ``store_base_commit`` and the dirty marker (#1400 CORE-010).

The local store is not free-floating: it is *anchored* to a commit. The relation
the whole reconcile spine rests on (I3, spec §2.2) is

    store == hydrate(projection @ store_base_commit) + replay(local_overlay)

and ``store_base_commit`` is the left-hand anchor — the commit the store was last
hydrated from. Without it, reconcile would have to *guess* which projection the
store's public half came from, and a wrong guess silently corrupts the replay.

So it is written on every hydrate and advanced **only** on a successful reconcile
(P001). A store whose base commit is absent, or names a commit that is not
reachable in this repository, is not reconcilable at all: it is re-hydratable, and
:mod:`atdd.state.reconcile` says so rather than reconciling against a guess.

Dependency discipline: stdlib + ``atdd.state`` only. No provider, no git — this
module only reads and writes the ``store_metadata`` table.
"""
from __future__ import annotations

import sqlite3
from typing import Optional

from atdd.state.db import current_version

#: The commit the store was last hydrated from (a 40-char sha, or absent).
BASE_COMMIT_KEY = "store_base_commit"

#: The ``source_generation`` a tombstone records when the store has no base commit yet
#: (#1580). A cold-start store can legitimately retire something before it is anchored,
#: and the retirement still has to say which generation it was decided in. "None" would
#: read as a missing field — an unattributable retirement — so the unanchored case is
#: named explicitly instead: it is a fact about the retirement, not an absence of one.
UNANCHORED_GENERATION = "unanchored"

#: The store's schema version at the last stamp — recorded alongside the base
#: commit so an operator reading the metadata sees *what* was hydrated as well as
#: *from where*.
SCHEMA_VERSION_KEY = "schema_version"

#: The dirty marker. ``clean`` after a hydrate or a successful reconcile; ``dirty``
#: while uncommitted overlay events are outstanding. It is a *cache* of
#: ``overlay_events``, never the authority — :func:`atdd.state.overlay.is_dirty`
#: reads the events themselves, so a stale marker can never lose local work.
DIRTY_KEY = "dirty"

DIRTY_CLEAN = "clean"
DIRTY_DIRTY = "dirty"


class StoreBaseCommitError(RuntimeError):
    """The store's base commit is absent or unresolvable, so reconcile cannot run.

    Carries the offending ``commit`` (``None`` when the metadata holds none) and
    tells the operator to re-hydrate: reconcile has no base to replay onto, and
    inventing one would replay the overlay against the wrong public state.
    """

    def __init__(self, message: str, *, commit: Optional[str] = None) -> None:
        self.commit = commit
        super().__init__(message)


def get(conn: sqlite3.Connection, key: str) -> Optional[str]:
    """The metadata value at ``key``, or ``None`` when it was never written."""
    row = conn.execute("SELECT value FROM store_metadata WHERE key=?", (key,)).fetchone()
    return None if row is None else row["value"]


def set(  # noqa: A001 — the table is a key/value map; `set` is its verb
    conn: sqlite3.Connection, key: str, value: Optional[str]
) -> None:
    """Write ``value`` at ``key`` (upsert)."""
    with conn:
        conn.execute(
            """
            INSERT INTO store_metadata (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (key, value),
        )


def base_commit(conn: sqlite3.Connection) -> Optional[str]:
    """The commit this store was last hydrated from, or ``None`` if never stamped."""
    return get(conn, BASE_COMMIT_KEY)


def stamp_base_commit(conn: sqlite3.Connection, commit: str, *, dirty: bool = False) -> None:
    """Anchor the store to ``commit`` and record the schema version and dirty marker.

    Called on every hydrate and on every *successful* reconcile — the two, and only
    two, moments at which the store's public half is known to equal the projection
    at a specific commit. Re-stamping the same commit is idempotent: the same value
    is rewritten and nothing else moves (P001).
    """
    set(conn, BASE_COMMIT_KEY, commit)
    set(conn, SCHEMA_VERSION_KEY, str(current_version(conn)))
    set(conn, DIRTY_KEY, DIRTY_DIRTY if dirty else DIRTY_CLEAN)


def mark_dirty(conn: sqlite3.Connection, dirty: bool = True) -> None:
    """Move the dirty marker. A hint for operators and hooks, never an authority."""
    set(conn, DIRTY_KEY, DIRTY_DIRTY if dirty else DIRTY_CLEAN)


def is_marked_dirty(conn: sqlite3.Connection) -> bool:
    """True when the *marker* says dirty. Prefer :func:`atdd.state.overlay.is_dirty`."""
    return get(conn, DIRTY_KEY) == DIRTY_DIRTY


def require_base_commit(conn: sqlite3.Connection) -> str:
    """The base commit, or raise :class:`StoreBaseCommitError` when it is absent.

    The caller must run this *before* touching sqlite or reading any projection, so
    a baseless store is refused without a single side effect (P001-UNIT-002).
    """
    commit = base_commit(conn)
    if not commit:
        raise StoreBaseCommitError(
            "the local store carries no store_base_commit, so there is no base "
            "projection to reconcile against — run `atdd state hydrate` to re-anchor it",
            commit=None,
        )
    return commit
