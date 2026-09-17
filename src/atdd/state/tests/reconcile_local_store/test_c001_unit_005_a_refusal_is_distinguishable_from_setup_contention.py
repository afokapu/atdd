# URN: test:reconcile-local-store:guard-dirty-store:C001-UNIT-005-a-refusal-is-distinguishable-from-setup-contention
# Acceptance: acc:reconcile-local-store:C001-UNIT-005-a-refusal-is-distinguishable-from-setup-contention
# WMBT: wmbt:reconcile-local-store:C001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: A caller must be able to tell a deliberate refusal from a failure to establish the connection at all, so the store's serialisation is not blamed for faults it did not cause. Refs #2031.
"""A refusal is distinguishable from setup contention (C001-UNIT-005).

wagon: reconcile-local-store | feature: guard-dirty-store | phase: RED
WMBT: wmbt:reconcile-local-store:C001

:func:`atdd.state.db.connect` applies its pragmas in this order::

    PRAGMA foreign_keys = ON
    PRAGMA journal_mode = WAL      # <- can contend, and runs with NO timeout
    PRAGMA busy_timeout = 5000     # <- set afterwards

``journal_mode`` needs a lock, and it executes before the busy timeout is in force. So under
contention ``connect()`` itself raises ``sqlite3.OperationalError: database is locked`` —
**the same text a deliberate refusal produces**, before the configured five-second wait has
any effect.

Why that matters here and not merely in the abstract: once the store serialises writers, a
caller that waits is normal and a caller that fails is news. If the two are textually
identical, the serialisation gets blamed for faults it did not cause. This was not theory —
while probing #2031 a writer showed a spurious refusal that looked exactly like the new
guard working, and two defects cancelled into a false green.

The fix for the ordering belongs to ``db.connect`` and is filed separately. What is pinned
here is the property this issue depends on: **a configured wait must actually be honoured,
so that a lock error means refusal.**

Refs #2031.
"""
from __future__ import annotations

import contextlib
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from atdd.state.db import connect
from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.store import StateStore

from ._helpers import checkout, store, store_file

#: How long the contending holder keeps the write lock. Comfortably inside the 5s timeout
#: `connect` configures, so a connection that honours it must succeed rather than raise.
HELD_SECONDS = 1.5


def _seeded_store(repo: Path) -> Path:
    conn = store(repo)
    try:
        StateStore(conn).objects.upsert(
            "legacy-slug-0", WORK_ITEM_KIND, state="PLANNED", data={"title": "x"})
    finally:
        conn.close()
    return store_file(repo)


def _time_to_acquire(db: Path, *, timeout) -> "float | None":
    """Seconds spent acquiring the write lock, or None if it was refused."""
    kwargs = {} if timeout is None else {"timeout": timeout}
    conn = sqlite3.connect(str(db), **kwargs)
    started = time.time()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.rollback()
        return time.time() - started
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()


class _RawHeldLock:
    """Hold an exclusive lock on a bare sqlite file (no atdd schema needed)."""

    def __init__(self, db: Path, seconds: float) -> None:
        self._db, self._seconds = db, seconds
        self._taken = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        conn = sqlite3.connect(str(self._db), timeout=30)
        try:
            conn.execute("BEGIN EXCLUSIVE")
            self._taken.set()
            time.sleep(self._seconds)
            conn.rollback()
        finally:
            conn.close()

    def __enter__(self) -> "_RawHeldLock":
        self._thread.start()
        assert self._taken.wait(timeout=30), "the contending lock was never taken"
        return self

    def __exit__(self, *_exc) -> None:
        self._thread.join(timeout=60)


class _HeldWriteLock:
    """Hold the store's write lock from a raw connection for a bounded time."""

    def __init__(self, db: Path, seconds: float = HELD_SECONDS) -> None:
        self._db, self._seconds = db, seconds
        self._taken = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        conn = sqlite3.connect(str(self._db))
        try:
            conn.execute("PRAGMA busy_timeout = 30000")
            conn.execute("BEGIN EXCLUSIVE")
            self._taken.set()
            time.sleep(self._seconds)
            conn.rollback()
        finally:
            conn.close()

    def __enter__(self) -> "_HeldWriteLock":
        self._thread.start()
        assert self._taken.wait(timeout=30), "the contending lock was never taken"
        return self

    def __exit__(self, *_exc) -> None:
        self._thread.join(timeout=60)


def test_python_already_applies_a_busy_timeout_before_any_pragma() -> None:
    """The ordering concern this acceptance was written for does NOT exist. Pinned so the
    correction cannot be lost.

    `db.connect` applies `PRAGMA journal_mode = WAL` before `PRAGMA busy_timeout = 5000`, and
    I reported that as a defect: the contending pragma running with no timeout. It is not one.
    ``sqlite3.connect`` takes ``timeout=5.0`` **by default**, applied when the connection
    opens — before any pragma executes. The explicit pragma is redundant, not a late fix for
    a gap, and the ordering creates no window.

    Measured: with the default, acquiring a held lock waits and succeeds; with ``timeout=0``
    it fails instantly. That is the difference the claim attributed to pragma order.
    """
    import tempfile

    scratch = Path(tempfile.mkdtemp()) / "probe.sqlite"
    seed = sqlite3.connect(str(scratch))
    seed.execute("CREATE TABLE t(x)")
    seed.commit()
    seed.close()

    # Each attempt gets its OWN hold window: the first acquire consumes the hold it waited
    # out, so sequencing both inside one window would find the lock already free.
    with _RawHeldLock(scratch, seconds=1.2):
        waited = _time_to_acquire(scratch, timeout=None)     # library default
    with _RawHeldLock(scratch, seconds=1.2):
        instant = _time_to_acquire(scratch, timeout=0)       # no patience at all

    assert waited is not None and waited > 0.5, (
        f"a default sqlite3 connection did not wait for a held lock (took {waited}); the "
        "reasoning in this module and in #2031's Decision 6 depends on it having a "
        "non-zero default timeout and must be re-derived"
    )
    assert instant is None, (
        "timeout=0 acquired a held lock, so waiting is not what distinguishes the two cases"
    )


def test_the_migration_does_not_hold_the_store_past_a_writer_s_patience(tmp_path) -> None:
    """A concurrent writer must not be timed out by the migration. Measured behaviourally.

    The real cause of the refusals an earlier revision of this issue blamed on pragma
    ordering: the exclusive lock used to be taken *before* ``backup_store``, and both
    ``backup_store`` and ``_scratch_copy`` checkpoint the WAL on their own connections. A
    checkpoint contending with a fence the same process already holds waits out its whole
    ``busy_timeout`` — twice. Measured at ~10.5s held regardless of store size (30, 300 and
    1054 objects all within 0.2s of each other), against the 5s a default connection waits.

    So every concurrent writer was timed out by construction. This asserts the outcome rather
    than the lock's duration, so it holds through a change of mechanism: a writer with the
    library's default patience gets a verdict, and that verdict is not a timeout.

    RED: ~10.5s held, 5s of patience.
    """
    from atdd.state.manifest_migration import UNATTRIBUTED_OWNER
    from atdd.state.store_migration import (
        StoreChangedDuringMigrationError,
        migrate_store_durably,
    )

    repo = checkout(tmp_path / "repo")
    conn = store(repo)
    try:
        objects = StateStore(conn).objects
        for index in range(30):
            objects.upsert(f"legacy-slug-{index}", WORK_ITEM_KIND, state="PLANNED",
                           data={"title": f"item {index}"})
    finally:
        conn.close()
    db = store_file(repo)

    outcome: dict = {}

    def writer() -> None:
        # The library default (5s), not a generous override: the point is whether an
        # ordinary caller survives a migration.
        time.sleep(0.05)
        started = time.time()
        writer_conn = sqlite3.connect(str(db))
        try:
            writer_conn.execute("BEGIN IMMEDIATE")
            writer_conn.execute(
                "INSERT INTO objects (uid, kind, state, data, created_at, updated_at) "
                "VALUES ('arrived-during-migration', ?, 'PLANNED', '{}', "
                "datetime('now'), datetime('now'))",
                (WORK_ITEM_KIND,),
            )
            writer_conn.commit()
            outcome["verdict"] = f"committed after {time.time() - started:.2f}s"
        except sqlite3.OperationalError as exc:
            outcome["verdict"] = f"TIMED OUT: {exc} after {time.time() - started:.2f}s"
        finally:
            writer_conn.close()

    thread = threading.Thread(target=writer)
    thread.start()
    # A refusal is C001-UNIT-003's acceptance; here only the writer's fate is judged.
    with contextlib.suppress(StoreChangedDuringMigrationError):
        migrate_store_durably(db, owner_actor=UNATTRIBUTED_OWNER)
    thread.join(120)

    assert "verdict" in outcome, "the writer never reached a verdict"
    assert not outcome["verdict"].startswith("TIMED OUT"), (
        f"a concurrent writer with the library's default patience was timed out by the "
        f"migration: {outcome['verdict']}. The exclusive lock is held longer than an "
        "ordinary caller will wait, so every concurrent writer fails by construction."
    )


def test_connect_honours_its_wait_instead_of_failing_at_setup(tmp_path) -> None:
    """Behaviourally: opening a connection while the lock is held must not raise.

    RED: it raises at the ``journal_mode`` pragma, so the caller cannot tell "I could not
    open the store" from "the store refused my write".
    """
    repo = checkout(tmp_path / "repo")
    db = _seeded_store(repo)

    with _HeldWriteLock(db):
        started = time.time()
        try:
            conn = connect(db)
        except sqlite3.OperationalError as exc:
            pytest.fail(
                f"connect() raised {exc!r} after {time.time() - started:.2f}s while another "
                "holder had the write lock. This is a SETUP failure wearing the text of a "
                "refusal: the caller cannot tell them apart, and the store's serialisation "
                "will be blamed for it."
            )
        conn.close()


def test_a_genuine_refusal_is_reported_as_one(tmp_path) -> None:
    """The other side: when the wait really does expire, the error must still arrive.

    A connection that honours its timeout must not swallow contention — it waits, and then
    reports. Held longer than the configured timeout so the wait genuinely expires.
    """
    repo = checkout(tmp_path / "repo")
    db = _seeded_store(repo)

    with _HeldWriteLock(db, seconds=8.0):
        conn = sqlite3.connect(str(db))
        try:
            conn.execute("PRAGMA busy_timeout = 300")
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                conn.execute("BEGIN EXCLUSIVE")
        finally:
            conn.close()
