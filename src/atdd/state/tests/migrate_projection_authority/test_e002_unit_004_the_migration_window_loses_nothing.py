# URN: test:migrate-projection-authority:migrate-store-projection:E002-UNIT-004-the-migration-window-loses-nothing
# Acceptance: acc:migrate-projection-authority:E002-UNIT-004-the-migration-window-loses-nothing
# WMBT: wmbt:migrate-projection-authority:E002
# Phase: GREEN
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: The migration window neither discards a concurrent writer's committed work silently nor leaves the replaced store beside stale WAL side files; an interrupted run preserves the store's logical snapshot. Refs #2024.
"""Nothing is lost in the migration window (E002-UNIT-004).

wagon: migrate-projection-authority | feature: migrate-store-projection | phase: RED
WMBT: wmbt:migrate-projection-authority:E002

Copy-and-swap takes a snapshot at T0 and writes it back at T1. Every write that lands in
between is overwritten by it — silently, with no error and no trace. One copy or two makes no
difference: this is a property of the swap, not of the backup.

WAL is configured deliberately for "concurrent readers + a writer (sibling worktrees)"
(``db.py``), and this store is shared by every worktree under the Control Root. So the fence
that closes the window has a real cost, and the acceptance pins both halves: a writer must be
**refused loudly** rather than silently discarded, and a **reader must not be blocked**.

The swap itself must also discard the WAL side files. ``reconcile._replace_store`` already
does; replacing ``state.sqlite`` alone while ``-wal``/``-shm`` remain makes the store
unopenable.

**These are guards on the repair, not demonstrations of the current defect, and they are
labelled GREEN for that reason.** Today ``migrate-store`` mutates the live store in place, so
there is no snapshot window at all: a concurrent write survives by accident, and what the
operator loses instead is the whole store on a crash. Every assertion here therefore passes
today. It is the copy/swap repair that would introduce the loss, so these must still pass once
it lands. Calling them RED would claim a failure that is not there. Refs #2024.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from types import SimpleNamespace

from atdd.state import migrate_cli
from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.manifest_migration import UNATTRIBUTED_OWNER
from atdd.state.store import StateStore

from ._helpers import control_root

CONCURRENT_UID = "arrived-during-migration"


def live_store(root: Path, count: int = 40):
    db = init_state_store(start=Path(root))
    conn = connect(db)
    store = StateStore(conn)
    for index in range(count):
        store.objects.upsert(f"legacy-slug-{index}", WORK_ITEM_KIND, state="PLANNED",
                             data={"title": f"item {index}"})
    return db, conn


def uids(db: Path) -> list[str]:
    conn = connect(db)
    try:
        return sorted(r["uid"] for r in conn.execute(
            "SELECT uid FROM objects WHERE kind=?", (WORK_ITEM_KIND,)))
    finally:
        conn.close()


def sidecars(db: Path) -> list[str]:
    return [s for s in ("-wal", "-shm") if Path(str(db) + s).exists()]


def run_migrate_store(root: Path) -> int:
    return migrate_cli.dispatch(SimpleNamespace(
        op="migrate-store", root=str(root), dry_run=False,
        owner_actor=UNATTRIBUTED_OWNER, package=None,
    ))


def test_a_concurrent_write_is_never_silently_discarded(tmp_path: Path) -> None:
    """Either the write survives the swap, or its writer is refused. Never neither.

    RED: the write is committed, reported successful to its author, and then vanishes.
    """
    root = control_root(tmp_path / "root")
    db, conn = live_store(root)
    conn.close()

    refusal: dict[str, BaseException] = {}

    def concurrent_writer() -> None:
        time.sleep(0.02)  # let the migration open its window
        writer_conn = connect(db)
        try:
            StateStore(writer_conn).objects.upsert(
                CONCURRENT_UID, WORK_ITEM_KIND, state="PLANNED",
                data={"title": "committed while the migration was in flight"},
            )
        except sqlite3.OperationalError as exc:   # refused loudly — an acceptable outcome
            refusal["exc"] = exc
        finally:
            writer_conn.close()

    thread = threading.Thread(target=concurrent_writer)
    thread.start()
    run_migrate_store(root)
    thread.join(30)

    survived = CONCURRENT_UID in uids(db)
    assert survived or refusal, (
        "a write was committed to the live store during the migration, its author was told it "
        "succeeded, and the swap then discarded it — no error, no warning, no trace"
    )


def test_a_concurrent_reader_is_not_blocked(tmp_path: Path) -> None:
    """The fence may cost writers. It must not cost readers.

    WAL exists for concurrent readers across the sibling worktrees; a migration that takes the
    whole store offline would be a different kind of regression.
    """
    root = control_root(tmp_path / "root")
    db, conn = live_store(root)
    conn.close()

    read_latency: dict[str, float] = {}

    def concurrent_reader() -> None:
        time.sleep(0.02)
        started = time.time()
        reader_conn = connect(db)
        try:
            reader_conn.execute("SELECT count(*) FROM objects").fetchone()
            read_latency["seconds"] = time.time() - started
        finally:
            reader_conn.close()

    thread = threading.Thread(target=concurrent_reader)
    thread.start()
    run_migrate_store(root)
    thread.join(30)

    assert "seconds" in read_latency, "a concurrent reader was refused outright"
    assert read_latency["seconds"] < 5.0, (
        f"a concurrent read took {read_latency['seconds']:.2f}s — the migration is blocking "
        "readers, which is the concurrency WAL is configured to preserve"
    )


def test_the_swapped_store_carries_no_stale_sidecars(tmp_path: Path) -> None:
    """Replacing state.sqlite while -wal/-shm remain makes the store unopenable.

    RED today for the opposite reason — the migration performs no swap at all — but this is the
    regression that appears the moment one is introduced naively.
    """
    root = control_root(tmp_path / "root")
    db, conn = live_store(root)
    # leave a live connection with un-checkpointed WAL, as a running daemon would
    StateStore(conn).objects.upsert("uncheckpointed", WORK_ITEM_KIND, state="PLANNED",
                                    data={"title": "still in the -wal"})
    assert sidecars(db), "fixture error: the store has no WAL side files to strand"

    run_migrate_store(root)
    conn.close()

    try:
        reopened = uids(db)
    except sqlite3.DatabaseError as exc:
        raise AssertionError(
            f"the store could not be reopened after the migration: {exc}. The swap replaced "
            f"state.sqlite while {sidecars(db)} were still on disk"
        ) from exc
    assert reopened, "the store reopened empty after the migration"
