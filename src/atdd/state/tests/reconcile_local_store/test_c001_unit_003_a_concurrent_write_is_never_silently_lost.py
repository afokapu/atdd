# URN: test:reconcile-local-store:guard-dirty-store:C001-UNIT-003-a-concurrent-write-is-never-silently-lost
# Acceptance: acc:reconcile-local-store:C001-UNIT-003-a-concurrent-write-is-never-silently-lost
# WMBT: wmbt:reconcile-local-store:C001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: A write committed by another process while the store migration is in flight must never be accepted and then discarded. The writer takes no lock and knows of none — a cooperating writer would prove only that two consenting processes can agree. Refs #2031.
"""A concurrent write is never silently lost (C001-UNIT-003).

wagon: reconcile-local-store | feature: guard-dirty-store | phase: RED
WMBT: wmbt:reconcile-local-store:C001

I5 says *reconcile is not overwrite*. The store migration broke it in miniature: it took
``BEGIN EXCLUSIVE`` across backup → migrate → swap, then **had** to release the fence before
moving the file — a connection held across the move strands ``-wal``/``-shm`` and yields
``database disk image is malformed``. A write committed in that interval was overwritten by
the move, with no error and no trace, and its author was told it succeeded.

**Three shapes of this test would pass while the defect stood, and all are excluded here.**

*Racing.* A writer that merely races is caught before the interval even opens — measured:
``refused: database is locked``. An acceptance asserting "survives or is refused" therefore
passes without reaching the defect. So this module does not race: it places the write at the
one moment that matters, via the ``_migrate_the_copy`` seam — after the working copy was
taken, before the result is applied.

*Cooperating.* A writer that takes whatever lock the fix introduces proves only that two
consenting processes can agree. So the writer here is a plain :meth:`ObjectStore.upsert` on a
plain connection, taking no lock and knowing of none — what every real caller does.

*Never writing.* A writer that fails before it writes proves nothing either, so the assertion
is conditioned on the writer's own verdict rather than on the absence of its row.

The invariant asserted is deliberately weaker than "the write survives": either it survives,
**or** the migration refuses because of it. What must never happen is accepted-then-discarded.

Refs #2031 / #1580.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

from atdd.state import store_migration as migration_module
from atdd.state.db import connect
from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.manifest_migration import UNATTRIBUTED_OWNER
from atdd.state.store import StateStore
from atdd.state.store_contents import UnknownStoreTableError
from atdd.state.store_migration import (
    StoreChangedDuringMigrationError,
    migrate_store_durably,
)

from ._helpers import checkout, store, store_file

#: The object the concurrent process commits. Absent afterwards means it was discarded.
MARK = "arrived-while-the-migration-ran"

def _legacy_store(repo: Path, count: int = 30) -> Path:
    """A live WAL-mode store of slug-keyed work items with no owner_actor — migratable."""
    conn = store(repo)
    try:
        objects = StateStore(conn).objects
        for index in range(count):
            objects.upsert(f"legacy-slug-{index}", WORK_ITEM_KIND, state="PLANNED",
                           data={"title": f"item {index}"})
    finally:
        conn.close()
    return store_file(repo)


def _uids(db: Path) -> list[str]:
    conn = connect(db)
    try:
        return sorted(row["uid"] for row in conn.execute(
            "SELECT uid FROM objects WHERE kind=?", (WORK_ITEM_KIND,)))
    finally:
        conn.close()


def _naive_writer_source(db: Path) -> str:
    """A separate process doing a plain store write. No lock. No awareness of one.

    A generous ``busy_timeout`` is set so a slow migration cannot time this writer out and
    turn a real verdict into a bare failure. It is *not* set to work around pragma ordering:
    ``sqlite3.connect`` already applies a 5s timeout by default before any pragma runs, which
    C001-UNIT-005 pins — an earlier revision of this issue claimed otherwise and was wrong.
    """
    return textwrap.dedent(f"""
        import sqlite3, sys, time
        sys.path.insert(0, {str(Path(__file__).resolve().parents[4])!r})
        from atdd.state.manifest_import import WORK_ITEM_KIND
        from atdd.state.store import StateStore
        conn = sqlite3.connect({str(db)!r}); conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 20000")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        started = time.time()
        try:
            StateStore(conn).objects.upsert(
                {MARK!r}, WORK_ITEM_KIND, state="PLANNED", data={{"t": "1"}})
            print(f"COMMITTED after {{time.time() - started:.2f}}s")
        except sqlite3.OperationalError as exc:
            print(f"REFUSED: {{exc}} after {{time.time() - started:.2f}}s")
        finally:
            conn.close()
    """)


@pytest.fixture()
def write_while_migrating(monkeypatch):
    """Commit a write to the live store from another process *during* the migration.

    The seam is ``_migrate_the_copy`` — the step that does the real work on the working copy
    and legitimately takes time. Patching it to run a writer first puts the write exactly
    where it matters: after the snapshot was taken, before the result is applied. No internal
    file-move detail is assumed, so this survives a change of mechanism.
    """
    real = migration_module._migrate_the_copy
    observed: dict = {}

    def install(db: Path) -> None:
        def patched(scratch, *, owner_actor):
            writer = subprocess.run(
                [sys.executable, "-c", _naive_writer_source(db)],
                capture_output=True, text=True, timeout=120,
            )
            observed["stdout"] = writer.stdout.strip()
            observed["stderr"] = writer.stderr
            return real(scratch, owner_actor=owner_actor)

        monkeypatch.setattr(migration_module, "_migrate_the_copy", patched)

    return install, observed


def test_a_write_committed_during_the_migration_is_not_discarded(
    tmp_path, write_while_migrating,
) -> None:
    """The invariant: accepted-then-discarded must never happen.

    Either the write survives, or the migration refuses because of it. What must not occur
    is the writer being told it succeeded and the write then vanishing.

    RED: the write landed in the post-fence interval and the file move overwrote it.
    """
    repo = checkout(tmp_path / "repo")
    db = _legacy_store(repo)
    install, observed = write_while_migrating
    install(db)

    refused = None
    try:
        migrate_store_durably(db, owner_actor=UNATTRIBUTED_OWNER)
    except StoreChangedDuringMigrationError as exc:
        refused = exc

    told_it_committed = observed.get("stdout", "").startswith("COMMITTED")
    assert observed.get("stdout"), f"the writer produced no verdict:\n{observed.get('stderr','')[-600:]}"
    survived = MARK in _uids(db)

    if told_it_committed:
        assert survived, (
            f"the writer was told {observed['stdout']!r} and its write is absent afterwards: "
            "committed, reported successful, then discarded with no error and no trace. "
            f"(migration refused: {refused!r})"
        )


def test_the_migration_refuses_rather_than_overwriting(
    tmp_path, write_while_migrating,
) -> None:
    """The mechanism behind that invariant, pinned so it cannot regress into a silent win.

    The working copy is a snapshot. Applying it after somebody else has written would
    overwrite them, so the apply is a compare-and-swap and refuses instead.
    """
    repo = checkout(tmp_path / "repo")
    db = _legacy_store(repo)
    install, observed = write_while_migrating
    install(db)

    with pytest.raises(StoreChangedDuringMigrationError):
        migrate_store_durably(db, owner_actor=UNATTRIBUTED_OWNER)

    assert observed["stdout"].startswith("COMMITTED"), observed
    assert MARK in _uids(db), "the refusal did not leave the concurrent write in place"


def test_the_migration_completes_when_nothing_interferes(tmp_path) -> None:
    """The other half: protecting the writer must not mean never migrating."""
    repo = checkout(tmp_path / "repo")
    db = _legacy_store(repo)

    result = migrate_store_durably(db, owner_actor=UNATTRIBUTED_OWNER)

    assert result.report.migrated, "no work item was migrated"
    remaining = [uid for uid in _uids(db) if not uid.startswith("wi_")]
    assert not remaining, f"the store still carries slug-shaped uids: {remaining[:3]}"


def test_a_concurrent_reader_is_not_blocked(tmp_path) -> None:
    """WAL exists for concurrent readers across the sibling worktrees. Keep it that way."""
    repo = checkout(tmp_path / "repo")
    db = _legacy_store(repo)
    latency: dict = {}

    def reader() -> None:
        time.sleep(0.05)
        started = time.time()
        conn = connect(db)
        try:
            conn.execute("SELECT count(*) FROM objects").fetchone()
            latency["seconds"] = time.time() - started
        finally:
            conn.close()

    thread = threading.Thread(target=reader)
    thread.start()
    migrate_store_durably(db, owner_actor=UNATTRIBUTED_OWNER)
    thread.join(60)

    assert "seconds" in latency, "a concurrent reader was refused outright"
    assert latency["seconds"] < 5.0, (
        f"a concurrent read took {latency['seconds']:.2f}s during the migration"
    )


def test_a_table_the_replacement_cannot_move_refuses_rather_than_dropping_it(
    tmp_path,
) -> None:
    """The same invariant one level up: rows are never accepted-then-discarded either.

    The replacement's statements are static text (``atdd.state.store_contents``) because
    ``coder.security.sql-injection`` is strict and table names cannot be bound as
    parameters. That trades a generated statement for a declared one, and the risk it
    buys is a schema migration adding a table nobody taught the replacement about — whose
    rows would then be deleted and never refilled. So the table list is still read from
    the *live* store, and a table with no statement pair stops the run.

    Lives here rather than in its own module because it is the same defect this acceptance
    exists for — a write that was committed and is then silently gone — reached by a
    different route.
    """
    repo = checkout(tmp_path / "repo")
    db = _legacy_store(repo)

    conn = connect(db)
    try:
        conn.execute("CREATE TABLE side_car (uid TEXT PRIMARY KEY, note TEXT)")
        conn.execute("INSERT INTO side_car (uid, note) VALUES (?, ?)", (MARK, "keep me"))
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(UnknownStoreTableError) as caught:
        migrate_store_durably(db, owner_actor=UNATTRIBUTED_OWNER)

    assert "side_car" in str(caught.value), caught.value

    conn = connect(db)
    try:
        surviving = conn.execute("SELECT note FROM side_car WHERE uid=?", (MARK,)).fetchone()
    finally:
        conn.close()
    assert surviving is not None, "the refusal dropped the rows it refused to move"

    assert any(uid.startswith("legacy-slug-") for uid in _uids(db)), (
        "the refusal left a half-migrated store rather than the one it started with"
    )
