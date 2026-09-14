#!/usr/bin/env python3
"""#2024 — does the proposed copy/swap repair actually deliver backup + atomicity?

Run from a checkout:
    PYTHONPATH=src python3 docs/spikes/labs/2024-migrate-store-durability/probe.py

This exercises the *repair*, not the diagnosis. The diagnosis (migrate_cli never calls
backup_store; upsert/rekey each open their own `with self._conn:`) is established by
reading the code. What was never measured is whether the proposed fix — migrate against a
backup_store() copy, re-inspect, swap — actually holds up.

Result when this was written, against origin/main @ 5529abf4:

  HOLDS   the backup is restorable (P1); a plain cp of a WAL store loses everything (P2);
          copy/swap migrates correctly (P3); an interrupted run leaves the live store
          byte-identical (P4); the outer-BEGIN alternative measurably does not compose (P7).

  BROKEN  a concurrent writer's committed writes are silently discarded by the swap (P5);
          replacing the .sqlite while -wal/-shm exist corrupts the store outright (P6).

  FIXES   close connections + checkpoint + unlink the sidecars before replacing (P8);
          hold BEGIN EXCLUSIVE across the whole window so a writer is refused loudly
          rather than silently lost (P9); conn.backup()/VACUUM INTO are WAL-safe by
          construction and emit a sidecar-free copy (P10).
"""
import hashlib
import shutil
import sqlite3
import tempfile
import threading
import time
from pathlib import Path

from atdd.state.db import connect, init_state_store
from atdd.state.reconcile import backup_store, checkpoint
from atdd.state.store import StateStore
from atdd.state.store_migration import WORK_ITEM_KIND, inspect_store, migrate_store


def newroot(tag):
    """A throwaway Control Root with an initialised State Store."""
    base = Path(tempfile.mkdtemp(prefix=f"dur-{tag}-"))
    (base / ".atdd" / "state").mkdir(parents=True)
    (base / ".atdd" / "config.yaml").write_text("{}\n")
    return base, init_state_store(start=base)


def seed(db, n):
    """A store of legacy slug-keyed work items with no owner_actor — migratable."""
    conn = connect(db)
    store = StateStore(conn)
    for i in range(n):
        store.objects.upsert(
            f"legacy-slug-{i}", WORK_ITEM_KIND, state="PLANNED", data={"title": f"item {i}"},
        )
    return conn, store


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def uids(db):
    conn = connect(db)
    try:
        return sorted(r["uid"] for r in conn.execute(
            "SELECT uid FROM objects WHERE kind=?", (WORK_ITEM_KIND,)))
    finally:
        conn.close()


def sidecars(db):
    return [s for s in ("-wal", "-shm") if Path(str(db) + s).exists()]


def banner(text):
    print("\n" + "=" * 78 + f"\n{text}\n" + "=" * 78)


def p1_backup_is_restorable():
    banner("P1 — is the backup restorable at all?")
    _, db = newroot("p1")
    conn, _ = seed(db, 50)
    before = uids(db)
    backup = backup_store(db)
    print(f"  live objects       : {len(before)}")
    print(f"  backup objects     : {len(uids(backup))}")
    print(f"  identical uid set  : {before == uids(backup)}")
    Path(db).write_bytes(Path(backup).read_bytes())  # restore
    print(f"  after restore-copy : {len(uids(db))} objects, identical={uids(db) == before}")
    conn.close()


def p2_wal_needs_the_checkpoint():
    banner("P2 — WAL: does a plain copy lose recent commits? does checkpoint fix it?")
    _, db = newroot("p2")
    conn, _ = seed(db, 10)
    print(f"  journal_mode       : {conn.execute('PRAGMA journal_mode').fetchone()[0]}")
    print(f"  sidecars present   : {sidecars(db)}")
    naive = Path(str(db) + ".naive")
    shutil.copy2(db, naive)  # the .sqlite only, no checkpoint
    print(f"  live objects       : {len(uids(db))}")
    print(f"  naive copy objects : {len(uids(naive))}   <- plain cp, no checkpoint")
    checkpoint(db)
    checked = Path(str(db) + ".checked")
    shutil.copy2(db, checked)
    print(f"  after checkpoint   : {len(uids(checked))}  <- what backup_store() does")
    conn.close()


def p3_copy_swap_end_to_end():
    banner("P3 — copy/swap end to end: migrate the COPY, re-inspect, swap")
    _, db = newroot("p3")
    conn, _ = seed(db, 30)
    pre = uids(db)
    conn.close()
    checkpoint(db)
    pre_digest = digest(db)
    backup = backup_store(db)                       # 1. back up
    copy_conn = connect(backup)
    report = migrate_store(copy_conn)               # 2. migrate the copy
    leftover = inspect_store(StateStore(copy_conn))  # 3. re-inspect the RESULT
    copy_conn.close()
    checkpoint(backup)
    print(f"  pre-migration uids : {len(pre)} (all slug-keyed)")
    print(f"  report             : {report.migrated} rekeyed, {len(report.attributed)} attributed")
    print(f"  re-inspect result  : {'CLEAN' if not leftover else leftover[:1]}")
    print(f"  live store unchanged before swap? {digest(db) == pre_digest}")
    Path(db).write_bytes(Path(backup).read_bytes())  # 4. swap
    post = uids(db)
    print(f"  after swap         : {len(post)} objects, "
          f"all contract-shaped={all(u.startswith('wi_') for u in post)}")


def p4_interruption_leaves_the_live_store_alone():
    banner("P4 — interruption: die mid-migration ON THE COPY")
    _, db = newroot("p4")
    conn, _ = seed(db, 30)
    conn.close()
    checkpoint(db)
    pre_digest, pre_uids = digest(db), uids(db)
    backup = backup_store(db)
    copy_conn = connect(backup)

    object_store_cls = StateStore(copy_conn).objects.__class__
    original_rekey, calls = object_store_cls.rekey, {"n": 0}

    def exploding_rekey(self, old_uid, new_uid):
        calls["n"] += 1
        if calls["n"] > 5:
            raise RuntimeError("simulated crash mid-migration (object 6)")
        return original_rekey(self, old_uid, new_uid)

    object_store_cls.rekey = exploding_rekey
    try:
        migrate_store(copy_conn)
    except RuntimeError as exc:
        print(f"  raised             : {exc}")
    finally:
        object_store_cls.rekey = original_rekey
        copy_conn.close()

    print(f"  live digest unchanged? {digest(db) == pre_digest}")
    print(f"  live uids unchanged?   {uids(db) == pre_uids}")
    rekeyed = len([u for u in uids(backup) if u.startswith("wi_")])
    print(f"  copy is half-migrated: {rekeyed} of {len(uids(backup))} rekeyed (discardable)")


def p5_concurrent_writer_is_silently_lost():
    banner("P5 — concurrent writer: someone writes to the LIVE store during the migration")
    _, db = newroot("p5")
    conn, _ = seed(db, 30)
    conn.close()
    checkpoint(db)
    backup = backup_store(db)  # backup taken at T0

    def concurrent_writer():
        writer_conn = connect(db)
        store = StateStore(writer_conn)
        for i in range(3):
            store.objects.upsert(
                f"arrived-during-migration-{i}", WORK_ITEM_KIND,
                state="PLANNED", data={"title": "written at T1"},
            )
            time.sleep(0.01)
        writer_conn.close()

    thread = threading.Thread(target=concurrent_writer)
    thread.start()
    copy_conn = connect(backup)
    migrate_store(copy_conn)
    copy_conn.close()
    checkpoint(backup)
    thread.join(10)

    concurrent = [u for u in uids(db) if u.startswith("arrived-during-migration")]
    print(f"  live store at swap time  : {len(uids(db))} objects")
    print(f"  written during migration : {len(concurrent)}")
    Path(db).write_bytes(Path(backup).read_bytes())  # swap
    survived = [u for u in uids(db) if u.startswith("arrived-during-migration")]
    print(f"  after swap               : {len(uids(db))} objects")
    print(f"  concurrent writes kept   : {len(survived)}")
    print(f"  => {'LOST' if not survived else 'preserved'} — "
          f"{len(concurrent)} committed write(s) discarded by the swap, silently")


def p6_stale_sidecars_corrupt_the_swap():
    banner("P6 — stale WAL sidecars: does swapping the .sqlite alone corrupt or rewind?")
    _, db = newroot("p6")
    conn, store = seed(db, 20)
    store.objects.upsert("uncheckpointed-write", WORK_ITEM_KIND,
                         state="PLANNED", data={"title": "still in the -wal"})
    print(f"  sidecars before swap : {sidecars(db)}  (live connection still open)")
    backup = backup_store(db)
    copy_conn = connect(backup)
    migrate_store(copy_conn)
    copy_conn.close()
    checkpoint(backup)
    Path(db).write_bytes(Path(backup).read_bytes())  # .sqlite only; sidecars left behind
    print(f"  sidecars after swap  : {sidecars(db)}")
    try:
        print(f"  reopened OK          : {len(uids(db))} objects")
    except sqlite3.DatabaseError as exc:
        print(f"  reopen FAILED        : {type(exc).__name__}: {exc}")
    conn.close()


def p7_outer_begin_does_not_compose():
    banner("P7 — the outer-BEGIN alternative, MEASURED")
    _, db = newroot("p7")
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


def p8_the_swap_done_correctly():
    banner("P8 — the swap done correctly: close + checkpoint + drop sidecars, then replace")
    _, db = newroot("p8")
    conn, store = seed(db, 20)
    store.objects.upsert("uncheckpointed-write", WORK_ITEM_KIND,
                         state="PLANNED", data={"title": "still in the -wal"})
    backup = backup_store(db)
    copy_conn = connect(backup)
    migrate_store(copy_conn)
    copy_conn.close()
    checkpoint(backup)
    print(f"  sidecars before swap : {sidecars(db)}")
    conn.close()          # every live connection closed FIRST
    checkpoint(db)        # fold the live WAL back in
    for suffix in ("-wal", "-shm"):
        stale = Path(str(db) + suffix)
        if stale.exists():
            stale.unlink()
    print(f"  after close+checkpoint+unlink : {sidecars(db)}")
    Path(db).write_bytes(Path(backup).read_bytes())
    try:
        post = uids(db)
        print(f"  reopened OK          : {len(post)} objects, "
              f"all contract-shaped={all(u.startswith('wi_') for u in post)}")
    except sqlite3.DatabaseError as exc:
        print(f"  reopen FAILED        : {type(exc).__name__}: {exc}")


def p9_exclusive_lock_refuses_the_writer_loudly():
    banner("P9 — does an exclusive lock stop the concurrent writer losing data silently?")
    _, db = newroot("p9")
    conn, _ = seed(db, 20)
    conn.close()
    checkpoint(db)
    gate = connect(db)
    gate.execute("BEGIN EXCLUSIVE")  # hold the store across the whole window
    print("  held BEGIN EXCLUSIVE on the live store")
    outcome = {}

    def writer():
        writer_conn = connect(db)  # busy_timeout = 5000, per db.connect()
        started = time.time()
        try:
            StateStore(writer_conn).objects.upsert(
                "arrived-during-migration", WORK_ITEM_KIND,
                state="PLANNED", data={"title": "T1"},
            )
            outcome["r"] = f"SUCCEEDED after {time.time() - started:.2f}s"
        except sqlite3.OperationalError as exc:
            outcome["r"] = f"{type(exc).__name__}: {exc} (after {time.time() - started:.2f}s)"
        finally:
            writer_conn.close()

    thread = threading.Thread(target=writer)
    thread.start()
    thread.join(15)
    print(f"  concurrent writer    : {outcome.get('r')}")
    refused = "locked" in str(outcome.get("r"))
    print(f"  => the writer is {'REFUSED loudly' if refused else 'admitted'},"
          " rather than silently discarded at swap time")
    gate.rollback()
    gate.close()


def p10_wal_safe_backup_mechanisms():
    banner("P10 — sqlite3 backup API / VACUUM INTO: WAL-safe without a manual checkpoint?")
    _, db = newroot("p10")
    conn, _ = seed(db, 15)  # writes still sitting in the -wal
    print(f"  sidecars             : {sidecars(db)}  (writes not yet checkpointed)")
    api_copy = Path(str(db) + ".apibak")
    destination = sqlite3.connect(str(api_copy))
    conn.backup(destination)
    destination.close()
    print(f"  conn.backup()        : {len(uids(api_copy))} objects  (plain cp gave 0 in P2)")
    vacuum_copy = Path(str(db) + ".vacbak")
    conn.execute(f"VACUUM INTO '{vacuum_copy}'")
    print(f"  VACUUM INTO          : {len(uids(vacuum_copy))} objects")
    print(f"  sidecars on copies   : api={sidecars(api_copy)} vacuum={sidecars(vacuum_copy)}")
    conn.close()


if __name__ == "__main__":
    for probe in (
        p1_backup_is_restorable,
        p2_wal_needs_the_checkpoint,
        p3_copy_swap_end_to_end,
        p4_interruption_leaves_the_live_store_alone,
        p5_concurrent_writer_is_silently_lost,
        p6_stale_sidecars_corrupt_the_swap,
        p7_outer_begin_does_not_compose,
        p8_the_swap_done_correctly,
        p9_exclusive_lock_refuses_the_writer_loudly,
        p10_wal_safe_backup_mechanisms,
    ):
        probe()
