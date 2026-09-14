#!/usr/bin/env python3
"""#2024 — does the durability repair actually preserve an undo? (adversarial-review rev)

Run from a checkout:
    PYTHONPATH=src python3 docs/spikes/labs/2024-migrate-store-durability/probe.py

Earlier revisions of this issue specified the repair as "migrate against a backup_store()
copy, re-inspect, swap". An adversarial review found that this destroys the undo it exists
to create: backup_store() returns the SOLE copied file (reconcile.py:381), so migrating it
means the alleged backup is itself migrated. R1 reproduces that.

The repo already ships the correct pattern, and this issue should reuse it rather than
invent one — reconcile.py does all three steps:

    backup  = backup_store(db_path)            # reconcile.py:847  immutable undo
    scratch = _scratch_copy(db_path, workdir)  # reconcile.py:877  separate mutable copy
    ...mutate the scratch...
    _replace_store(scratch, db_path)           # reconcile.py:936  unlink -wal/-shm, move

Result when this was written, against origin/main @ 5529abf4:

  R1  one-copy design: after a successful run the "backup" is MIGRATED — no undo exists.
  R2  two-copy pattern: the backup is byte-identical to the pre-run store. Undo preserved.
  R3  "byte-identical to its pre-run state" is ill-defined on a live WAL store: backup_store
      checkpoints first (reconcile.py:389 -> 365), which changes state.sqlite's bytes before
      the migration starts. Preservation must be defined logically, over the snapshot.
  R4  a concurrent writer is still lost — the scratch is a snapshot at T0 and copy/swap
      overwrites anything committed after it. One copy or two makes no difference here.
  R5  BEGIN EXCLUSIVE fences the writer loudly, but it also blocks other WRITERS across the
      114+ worktrees WAL exists to serve (db.py:9). That is the cost to weigh, not a free fix.
  R6  _replace_store already unlinks the sidecars; the naive write_bytes swap corrupts.
  R7  the outer-BEGIN alternative measurably does not compose: the write survives rollback().
  R8  restoring the backup returns the pre-run store — compared over the snapshot, which is
      the acceptance to write. Byte-identity of the live file is not available (R2, R3).
"""
import hashlib
import shutil
import sqlite3
import tempfile
import threading
import time
from pathlib import Path

from atdd.state.db import connect, init_state_store
from atdd.state.reconcile import _replace_store, _scratch_copy, backup_store, checkpoint
from atdd.state.store import StateStore
from atdd.state.store_migration import WORK_ITEM_KIND, inspect_store, migrate_store


def newroot(tag):
    base = Path(tempfile.mkdtemp(prefix=f"dur-{tag}-"))
    (base / ".atdd" / "state").mkdir(parents=True)
    (base / ".atdd" / "config.yaml").write_text("{}\n")
    return base, init_state_store(start=base)


def seed(db, n):
    """Legacy slug-keyed work items with no owner_actor — migratable."""
    conn = connect(db)
    store = StateStore(conn)
    for i in range(n):
        store.objects.upsert(
            f"legacy-slug-{i}", WORK_ITEM_KIND, state="PLANNED", data={"title": f"item {i}"},
        )
    return conn, store


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


#: Every table the store's content lives in. schema_migrations and sqlite_sequence are
#: deliberately excluded: they are bookkeeping, identical across any two stores at the same
#: schema version, and including them would make the comparison look stronger than it is.
SNAPSHOT_TABLES = (
    "objects", "relationships", "events", "external_refs",
    "overlay_events", "inbox", "outbox", "store_metadata",
)


def snapshot(db):
    """The store's LOGICAL content: every row of every content table, order-independent.

    This is what "the store was preserved" has to mean on a WAL database. It cannot mean the
    bytes of state.sqlite: backup_store checkpoints the live file before copying it, so the
    bytes move before any migration runs (R3).
    """
    conn = connect(db)
    try:
        return {
            table: sorted(tuple(row) for row in conn.execute(f"SELECT * FROM {table}"))
            for table in SNAPSHOT_TABLES
        }
    finally:
        conn.close()


def uids(db):
    conn = connect(db)
    try:
        return sorted(r["uid"] for r in conn.execute(
            "SELECT uid FROM objects WHERE kind=?", (WORK_ITEM_KIND,)))
    finally:
        conn.close()


def shape(db):
    got = uids(db)
    minted = len([u for u in got if u.startswith("wi_")])
    return f"{len(got)} objects, {minted} contract-shaped, {len(got) - minted} slug-keyed"


def sidecars(db):
    return [s for s in ("-wal", "-shm") if Path(str(db) + s).exists()]


def banner(text):
    print("\n" + "=" * 78 + f"\n{text}\n" + "=" * 78)


def r1_one_copy_destroys_the_undo():
    banner("R1 — the design this issue ORIGINALLY specified: migrate the backup itself")
    _, db = newroot("r1")
    conn, _ = seed(db, 30)
    conn.close()
    checkpoint(db)
    pre_digest, pre = digest(db), uids(db)

    backup = backup_store(db)              # the ONLY copy
    copy_conn = connect(backup)
    migrate_store(copy_conn)               # ...and we migrate it
    copy_conn.close()
    checkpoint(backup)
    Path(db).write_bytes(Path(backup).read_bytes())

    print(f"  pre-run store        : {len(pre)} objects, all slug-keyed")
    print(f"  live store after     : {shape(db)}")
    print(f"  the 'backup' now     : {shape(backup)}")
    print(f"  backup == pre-run?   : {digest(backup) == pre_digest}")
    print("  => the undo is GONE: the only backup was migrated in place.")
    print("     Nothing on disk still holds the pre-migration store.")


def r2_two_copies_preserve_the_undo():
    banner("R2 — the repo's actual pattern: backup_store + _scratch_copy + _replace_store")
    _, db = newroot("r2")
    conn, _ = seed(db, 30)

    # NO pre-checkpoint. A real store is live: a connection is open and recent commits are
    # still in the -wal. An earlier revision of this probe checkpointed here before taking
    # the "pre-run" digest, which quietly made backup_store's own checkpoint a no-op and let
    # a byte-identity claim pass that cannot hold in the real case.
    print(f"  sidecars at rest     : {sidecars(db)}  (live connection open)")
    pre_bytes = digest(db)
    pre_snapshot = snapshot(db)
    pre_uids = uids(db)

    backup = backup_store(db)                       # immutable undo (reconcile.py:847)
    print(f"  pre-run state.sqlite digest : {pre_bytes}")
    print(f"  backup digest               : {digest(backup)}")
    print(f"  backup == pre-run BYTES?    : {digest(backup) == pre_bytes}"
          "   <- False: backup_store checkpointed the live file first")
    print(f"  backup == pre-run SNAPSHOT? : {snapshot(backup) == pre_snapshot}"
          "   <- the property that actually holds")

    with tempfile.TemporaryDirectory() as tmp:
        scratch = _scratch_copy(db, Path(tmp))      # separate mutable copy (:877)
        scratch_conn = connect(scratch)
        report = migrate_store(scratch_conn)
        leftover = inspect_store(StateStore(scratch_conn))
        scratch_conn.close()
        checkpoint(scratch)
        print(f"  migrated on scratch  : {report.migrated} rekeyed, re-inspect="
              f"{'CLEAN' if not leftover else leftover[:1]}")
        conn.close()
        _replace_store(scratch, db)                 # unlink sidecars + move (:936)

    print(f"  live after swap      : {shape(db)}")
    print(f"  backup after swap    : {shape(backup)}")
    print(f"  backup snapshot still == pre-run? {snapshot(backup) == pre_snapshot}")
    print(f"  backup uids still == pre-run?     {uids(backup) == pre_uids}")
    print("  => the undo survives a successful migration — stated over the SNAPSHOT.")
    print("     Byte-identity of the live file is not available and never was (see R3);")
    print("     the assertion to require is logical preservation + restorability (R8).")


def r3_byte_identical_is_ill_defined():
    banner("R3 — is 'the live store is left byte-identical' even well-defined on WAL?")
    _, db = newroot("r3")
    conn, store = seed(db, 20)
    # a live connection with writes still sitting in the -wal, as a real store has
    store.objects.upsert("written-not-checkpointed", WORK_ITEM_KIND,
                         state="PLANNED", data={"title": "in the -wal"})
    before = digest(db)
    before_objects = len(uids(db))
    print(f"  sidecars                     : {sidecars(db)}")
    print(f"  state.sqlite digest before    : {before}")
    backup_store(db)   # checkpoints the LIVE store first (reconcile.py:389 -> 365)
    after = digest(db)
    print(f"  state.sqlite digest after     : {after}")
    print(f"  bytes changed by merely backing up? {before != after}")
    print(f"  logical content unchanged?          {len(uids(db)) == before_objects}")
    print("  => backup_store mutates state.sqlite before any migration runs, so a")
    print("     'byte-identical' success criterion fails on a correct implementation.")
    print("     Preservation has to be defined over the SNAPSHOT (object set / content),")
    print("     not the file's bytes.")
    conn.close()


def r4_concurrent_writer_is_still_lost():
    banner("R4 — does the two-copy pattern save a concurrent writer? (no)")
    _, db = newroot("r4")
    conn, _ = seed(db, 30)
    conn.close()
    checkpoint(db)
    backup_store(db)

    def writer():
        writer_conn = connect(db)
        store = StateStore(writer_conn)
        for i in range(3):
            store.objects.upsert(f"arrived-during-migration-{i}", WORK_ITEM_KIND,
                                 state="PLANNED", data={"title": "written at T1"})
            time.sleep(0.01)
        writer_conn.close()

    with tempfile.TemporaryDirectory() as tmp:
        scratch = _scratch_copy(db, Path(tmp))   # snapshot at T0
        thread = threading.Thread(target=writer)
        thread.start()
        scratch_conn = connect(scratch)
        migrate_store(scratch_conn)
        scratch_conn.close()
        checkpoint(scratch)
        thread.join(10)
        arrived = [u for u in uids(db) if u.startswith("arrived-during-migration")]
        print(f"  committed to the live store during the migration: {len(arrived)}")
        _replace_store(scratch, db)
    survived = [u for u in uids(db) if u.startswith("arrived-during-migration")]
    print(f"  surviving the swap                               : {len(survived)}")
    print(f"  => {'LOST' if not survived else 'preserved'} — the scratch is a snapshot at T0;")
    print("     one copy or two makes no difference. This needs a lock or a fence.")


def r5_exclusive_lock_and_its_cost():
    banner("R5 — BEGIN EXCLUSIVE fences the writer, but what does it cost?")
    _, db = newroot("r5")
    conn, _ = seed(db, 20)
    conn.close()
    checkpoint(db)
    gate = connect(db)
    gate.execute("BEGIN EXCLUSIVE")
    print("  held BEGIN EXCLUSIVE on the live store")
    results = {}

    def attempt(label, fn):
        started = time.time()
        try:
            fn()
            results[label] = f"SUCCEEDED after {time.time() - started:.2f}s"
        except sqlite3.OperationalError as exc:
            results[label] = f"{type(exc).__name__}: {exc} (after {time.time() - started:.2f}s)"

    def do_write():
        c = connect(db)
        try:
            StateStore(c).objects.upsert("arrived", WORK_ITEM_KIND,
                                         state="PLANNED", data={"title": "T1"})
        finally:
            c.close()

    def do_read():
        c = connect(db)
        try:
            c.execute("SELECT count(*) FROM objects").fetchone()
        finally:
            c.close()

    for label, fn in (("another writer", do_write), ("another reader", do_read)):
        thread = threading.Thread(target=attempt, args=(label, fn))
        thread.start()
        thread.join(15)
        print(f"  {label:<16}: {results[label]}")
    print("  => writers are refused loudly rather than silently discarded — but they ARE")
    print("     refused, across every worktree sharing this store. WAL is configured")
    print("     precisely for 'concurrent readers + a writer (sibling worktrees)' (db.py:9),")
    print("     so the fence is an operational trade, not a free correctness win.")
    gate.rollback()
    gate.close()


def r6_replace_store_vs_naive_swap():
    banner("R6 — _replace_store already handles the sidecars; the naive swap does not")
    for label, naive in (("naive write_bytes", True), ("_replace_store", False)):
        _, db = newroot("r6")
        conn, store = seed(db, 20)
        store.objects.upsert("uncheckpointed", WORK_ITEM_KIND,
                             state="PLANNED", data={"title": "in the -wal"})
        with tempfile.TemporaryDirectory() as tmp:
            scratch = _scratch_copy(db, Path(tmp))
            scratch_conn = connect(scratch)
            migrate_store(scratch_conn)
            scratch_conn.close()
            checkpoint(scratch)
            if naive:
                Path(db).write_bytes(Path(scratch).read_bytes())
            else:
                conn.close()
                _replace_store(scratch, db)
        try:
            print(f"  {label:<20}: reopened OK — {shape(db)}")
        except sqlite3.DatabaseError as exc:
            print(f"  {label:<20}: FAILED — {type(exc).__name__}: {exc}")
        if naive:
            conn.close()


def r7_outer_begin_does_not_compose():
    """The alternative repair for defect 2, measured rather than asserted."""
    banner("R7 — the outer-BEGIN alternative, MEASURED")
    _, db = newroot("r7")
    conn, store = seed(db, 10)
    print(f"  isolation_level                    : {conn.isolation_level!r}")
    conn.execute("BEGIN")
    print(f"  in_transaction after explicit BEGIN: {conn.in_transaction}")
    store.objects.upsert("legacy-slug-0", WORK_ITEM_KIND, state="PLANNED",
                         data={"title": "touched inside the outer BEGIN"})
    print(f"  in_transaction after one upsert()  : {conn.in_transaction}"
          "   <- False: the inner `with conn:` COMMITTED the outer txn")
    other = connect(db)
    query = "SELECT json_extract(data,'$.title') t FROM objects WHERE uid=?"
    seen = other.execute(query, ("legacy-slug-0",)).fetchone()[0]
    print(f"  visible to another connection now  : {seen!r}")
    conn.rollback()
    still = other.execute(query, ("legacy-slug-0",)).fetchone()[0]
    print(f"  after rollback of the 'outer' txn  : {still!r}")
    print(f"  => outer BEGIN {'DOES NOT compose' if still == seen else 'composes'}"
          " — the write survived the rollback")
    other.close()
    conn.close()


def r8_restoring_from_the_backup_returns_the_store():
    """Preservation is only worth anything if the backup can be restored. Measure that."""
    banner("R8 — restorability: does restoring from the backup return the pre-run store?")
    _, db = newroot("r8")
    conn, _ = seed(db, 25)
    # again: live connection, un-checkpointed WAL, no kindness to the measurement
    pre_snapshot = snapshot(db)
    backup = backup_store(db)

    with tempfile.TemporaryDirectory() as tmp:
        scratch = _scratch_copy(db, Path(tmp))
        scratch_conn = connect(scratch)
        migrate_store(scratch_conn)
        scratch_conn.close()
        checkpoint(scratch)
        conn.close()
        _replace_store(scratch, db)
    print(f"  after migration      : {shape(db)}")
    print(f"  live == pre-run snapshot? {snapshot(db) == pre_snapshot}  (expected False)")

    # the operator's undo: put the backup back the same way the swap puts the scratch back
    with tempfile.TemporaryDirectory() as tmp:
        restored = Path(tmp) / "state.sqlite"
        shutil.copy2(backup, restored)
        _replace_store(restored, db)
    print(f"  after restore        : {shape(db)}")
    print(f"  live == pre-run snapshot? {snapshot(db) == pre_snapshot}  (expected True)")
    print("  => this is the acceptance to write: restore the backup, compare the SNAPSHOT.")


if __name__ == "__main__":
    for probe in (
        r1_one_copy_destroys_the_undo,
        r2_two_copies_preserve_the_undo,
        r3_byte_identical_is_ill_defined,
        r4_concurrent_writer_is_still_lost,
        r5_exclusive_lock_and_its_cost,
        r6_replace_store_vs_naive_swap,
        r7_outer_begin_does_not_compose,
        r8_restoring_from_the_backup_returns_the_store,
    ):
        probe()
