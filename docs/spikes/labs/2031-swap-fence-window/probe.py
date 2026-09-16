#!/usr/bin/env python3
"""#2031 — the store swap's residual fence window: is it real, how wide, and can a lock close it?

Run from a checkout:
    PYTHONPATH=src python3 docs/spikes/labs/2031-swap-fence-window/probe.py

`migrate_store_durably` holds `BEGIN EXCLUSIVE` across backup -> migrate -> swap, then MUST
release it before `reconcile._replace_store` moves the file: holding a connection open across
the move is what strands the WAL side files and yields `database disk image is malformed`.
That leaves a window between `fence.close()` and `shutil.move` in which a write can commit
and then be overwritten.

Every probe runs against throwaway WAL-mode stores. The live Control Root is never touched.

Result when this was written, against origin/main:

  P1  RACE     a writer racing the swap is REFUSED by the fence — so a racing acceptance
               PASSES and demonstrates nothing. This is the trap.
  P2  SUSPEND  with the window held open, the write COMMITS, the store genuinely holds it,
               and the swap then discards it. Silent: no error, no trace.
  P3  WIDTH    the window is bounded below by _replace_store (unlink sidecars + move).
  P4  LOCK     a Control-Root flock closes it across PROCESSES and across WORKTREES.
  P5  STALE    a killed holder does NOT leave a stale lock — flock is released by the kernel.
"""
import errno
import fcntl
import os
import signal
import statistics
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
from pathlib import Path

from atdd.state import reconcile
from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.manifest_migration import UNATTRIBUTED_OWNER
from atdd.state.store import StateStore
from atdd.state.store_migration import migrate_store_durably

MARK = "arrived-in-the-window"


def report_target_store() -> None:
    """Say out loud which store this run reasons about, and refuse a decoy.

    A reviewer of this lab read `main/.atdd/state/state.sqlite` — a 0-byte, 0-table file that
    `resolve_control_root` does NOT select — and concluded the scope arithmetic was
    unverifiable. They were reading a decoy beside the real Control Root store. The resolver
    is right; the ambiguity is in the filesystem, so the probe names the file it opened and
    refuses to reason from an empty one rather than leaving the next reader to repeat it.

    Every *measurement* below runs against throwaway stores; this is only the store the
    SCOPE claims (work-item counts, overlay state) are read from.
    """
    from atdd.state.paths import ControlRootNotFoundError, resolve_control_root

    print("target store for scope claims")
    print("-" * 76)
    try:
        resolution = resolve_control_root(Path.cwd())
    except ControlRootNotFoundError as exc:
        print(f"  no Control Root above {Path.cwd()}: {exc}")
        print("  scope claims in the issue CANNOT be verified from here.")
        return
    store = resolution.state_store_path
    print(f"  control root : {resolution.control_root}  ({resolution.layout_mode.value})")
    print(f"  store        : {store}")
    if not store.is_file():
        print("  REFUSING: the resolved store does not exist. Scope claims unverifiable here.")
        return
    size = store.stat().st_size
    conn = connect(store)
    try:
        tables = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
        if not tables:
            print(f"  REFUSING: {store} is {size} bytes with no tables — an empty decoy, not")
            print("  the Control Root store. Do not read scope arithmetic out of it.")
            return
        items = conn.execute(
            "SELECT count(*) FROM objects WHERE kind=?", (WORK_ITEM_KIND,)).fetchone()[0]
        overlay = conn.execute("SELECT count(*) FROM overlay_events").fetchone()[0]
    finally:
        conn.close()
    print(f"  size/tables  : {size} bytes, {tables} tables")
    print(f"  work items   : {items}")
    print(f"  overlay events: {overlay}  "
          f"({'CLEAN — reconcile hydrates and never swaps' if not overlay else 'DIRTY — reconcile would swap'})")

    decoy = resolution.control_root / "main" / ".atdd" / "state" / "state.sqlite"
    if decoy.is_file() and decoy.stat().st_size == 0:
        print(f"  NOTE: a 0-byte decoy also exists at {decoy}")
        print("        resolve_control_root does NOT select it. Do not read it by path.")


def control_root(tag: str) -> Path:
    root = Path(tempfile.mkdtemp(prefix=f"2031-{tag}-"))
    (root / ".atdd" / "state").mkdir(parents=True)
    (root / ".atdd" / "config.yaml").write_text("version: '1.0'\n")
    return root


def seeded_store(tag: str, n: int = 40, body: str = "") -> Path:
    """A WAL-mode store of legacy slug-keyed work items — migratable, throwaway."""
    db = init_state_store(start=control_root(tag))
    conn = connect(db)
    store = StateStore(conn)
    for index in range(n):
        data = {"title": f"item {index}"}
        if body:
            data["body"] = body
        store.objects.upsert(f"legacy-slug-{index}", WORK_ITEM_KIND, state="PLANNED", data=data)
    conn.close()
    return db


def uids(db: Path):
    conn = connect(db)
    try:
        return sorted(r["uid"] for r in conn.execute(
            "SELECT uid FROM objects WHERE kind=?", (WORK_ITEM_KIND,)))
    finally:
        conn.close()


def commit_one(db: Path, label: str) -> str:
    """Commit a single object. 'committed', or 'refused: ...' if the fence caught us."""
    conn = connect(db)
    try:
        StateStore(conn).objects.upsert(
            label, WORK_ITEM_KIND, state="PLANNED", data={"t": "1"})
        return "committed"
    except Exception as exc:  # sqlite3.OperationalError: database is locked
        return f"refused: {exc}"
    finally:
        conn.close()


def banner(text: str) -> None:
    print("\n" + "=" * 76 + f"\n{text}\n" + "=" * 76)


def _run_arm(tag: str, suspend: bool) -> dict:
    """Drive a real migration; optionally hold the window open around the move."""
    db = seeded_store(tag)
    before = len(uids(db))
    window_open, write_done = threading.Event(), threading.Event()
    seen: dict = {}
    real = reconcile._replace_store

    def patched(scratch, db_path):
        if suspend:
            window_open.set()          # the fence is ALREADY released here
            write_done.wait(timeout=20)
        return real(scratch, db_path)

    reconcile._replace_store = patched
    try:
        thread = threading.Thread(
            target=lambda: migrate_store_durably(db, owner_actor=UNATTRIBUTED_OWNER))
        thread.start()
        if suspend:
            window_open.wait(timeout=30)
            seen["write"] = commit_one(db, MARK)
            seen["in_window"] = len(uids(db))
            seen["visible"] = MARK in uids(db)
            write_done.set()
        else:
            time.sleep(0.01)
            seen["write"] = commit_one(db, MARK)
        thread.join(120)
    finally:
        reconcile._replace_store = real

    after = uids(db)
    return {**seen, "before": before, "after": len(after), "survived": MARK in after}


def p1_racing_proves_nothing():
    banner("P1 — RACE: a writer races the swap, uncoordinated (the naive acceptance)")
    r = _run_arm("race", suspend=False)
    print(f"  writer observed   : {str(r['write'])[:58]}")
    print(f"  objects           : {r['before']} -> {r['after']}")
    print(f"  write survived    : {r['survived']}")
    print("  => the fence caught it BEFORE the window. An acceptance asserting")
    print("     'survives or is refused' PASSES here while the defect is untouched.")


def p2_the_window_loses_a_committed_write():
    banner("P2 — SUSPEND: the write lands inside the window")
    r = _run_arm("suspend", suspend=True)
    print(f"  writer observed   : {str(r['write'])[:58]}")
    print(f"  during the window : {r.get('in_window')} objects, write visible={r.get('visible')}")
    print(f"  after the swap    : {r['after']} objects")
    print(f"  write survived    : {r['survived']}")
    print("  => the store genuinely HELD the write, then the move discarded it.")
    print("     Committed, reported successful, gone. No error, no trace.")


def p3_how_wide_is_the_window():
    banner("P3 — WIDTH: how long is the swap exposed?")
    real = reconcile._replace_store
    print(f"  {'objects':>8} {'store KB':>9} {'median ms':>11} {'min':>8} {'max':>8}")
    print("  " + "-" * 48)
    for n in (40, 400, 1047):
        spans, size_kb = [], 0
        for _ in range(3):
            db = seeded_store(f"w{n}", n, body="x" * 400)
            size_kb = Path(db).stat().st_size // 1024
            marks: dict = {}

            def timed(scratch, db_path, _marks=marks):
                _marks["in"] = time.perf_counter()
                out = real(scratch, db_path)
                _marks["out"] = time.perf_counter()
                return out

            reconcile._replace_store = timed
            try:
                migrate_store_durably(db, owner_actor=UNATTRIBUTED_OWNER)
            finally:
                reconcile._replace_store = real
            spans.append((marks["out"] - marks["in"]) * 1000)
        print(f"  {n:>8} {size_kb:>9} {statistics.median(spans):>11.3f} "
              f"{min(spans):>8.3f} {max(spans):>8.3f}")
    print("  => bounded below by _replace_store: unlink -wal/-shm, then shutil.move.")
    print("     The gap from fence.close() to that call is a few Python statements.")


def p4_a_control_root_lock_closes_it(src: str):
    banner("P4 — LOCK: does a Control-Root flock close it across PROCESSES and WORKTREES?")
    root = control_root("xproc")
    for worktree in ("wt-a", "wt-b"):
        (root / worktree).mkdir()
    lock = root / ".atdd" / "state" / "store.lock"

    seed = textwrap.dedent(f"""
        import sys; sys.path.insert(0, {src!r})
        from atdd.state.db import connect, init_state_store
        from atdd.state.manifest_import import WORK_ITEM_KIND
        from atdd.state.store import StateStore
        db = init_state_store(start={str(root)!r})
        c = connect(db); s = StateStore(c)
        for i in range(200):
            s.objects.upsert(f"legacy-slug-{{i}}", WORK_ITEM_KIND, state="PLANNED",
                             data={{"title": str(i)}})
        c.close(); print(db)
    """)
    db = subprocess.run([sys.executable, "-c", seed], capture_output=True, text=True).stdout.strip()

    migrator = textwrap.dedent(f"""
        import fcntl, sys, time
        sys.path.insert(0, {src!r})
        from atdd.state import reconcile
        from atdd.state.manifest_migration import UNATTRIBUTED_OWNER
        from atdd.state.store_migration import migrate_store_durably
        real = reconcile._replace_store
        def held(scratch, db_path):
            time.sleep(3.0)                 # hold the window open, lock still held
            return real(scratch, db_path)
        reconcile._replace_store = held
        h = open({str(lock)!r}, "a+")
        fcntl.flock(h.fileno(), fcntl.LOCK_EX)
        try:
            migrate_store_durably({db!r}, owner_actor=UNATTRIBUTED_OWNER)
        finally:
            fcntl.flock(h.fileno(), fcntl.LOCK_UN); h.close()
        print("done")
    """)

    writer = textwrap.dedent(f"""
        import errno, fcntl, sys
        sys.path.insert(0, {src!r})
        from atdd.state.db import connect
        from atdd.state.manifest_import import WORK_ITEM_KIND
        from atdd.state.store import StateStore
        h = open({str(lock)!r}, "a+")
        try:
            fcntl.flock(h.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            if e.errno in (errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK):
                print("REFUSED: the Control Root lock is held by another process")
                raise SystemExit(0)
            raise
        c = connect({db!r})
        StateStore(c).objects.upsert({MARK!r}, WORK_ITEM_KIND, state="PLANNED", data={{"t":"1"}})
        c.close()
        fcntl.flock(h.fileno(), fcntl.LOCK_UN); h.close()
        print("COMMITTED — the lock was free")
    """)

    proc = subprocess.Popen([sys.executable, "-c", migrator], cwd=str(root / "wt-a"),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(1.5)  # migrator is inside the held window
    writer_run = subprocess.run([sys.executable, "-c", writer], cwd=str(root / "wt-b"),
                                capture_output=True, text=True, timeout=120)
    proc.wait(timeout=120)

    conn = connect(db)
    present = conn.execute(
        "SELECT count(*) FROM objects WHERE uid=?", (MARK,)).fetchone()[0]
    total = conn.execute(
        "SELECT count(*) FROM objects WHERE kind=?", (WORK_ITEM_KIND,)).fetchone()[0]
    conn.close()

    print("  migrator runs in  : wt-a   (holds the lock across the whole swap)")
    print("  writer runs in    : wt-b   (different worktree, same Control Root)")
    observed = writer_run.stdout.strip()
    refused = observed.startswith("REFUSED")
    committed = observed.startswith("COMMITTED")
    print(f"  writer observed   : {observed or writer_run.stderr.strip().splitlines()[-1][:70]}")
    print(f"  final store       : {total} objects, window write present={bool(present)}")

    # The write being ABSENT proves nothing on its own — a writer that crashed also
    # writes nothing. The claim is that the lock REFUSED it, so that is what is asserted.
    if writer_run.returncode != 0 or not (refused or committed):
        print("  => INCONCLUSIVE — the writer did not run to a verdict:")
        for line in (writer_run.stderr or "").strip().splitlines()[-3:]:
            print(f"       {line[:88]}")
        print("     An absent write here means the writer FAILED, not that the lock held.")
        return
    if refused and not present:
        print("  => CLOSED across processes and worktrees — the writer was refused by the lock")
    elif committed and present:
        print("  => STILL OPEN — the writer committed inside the window and it survived")
    else:
        print(f"  => UNEXPECTED: refused={refused} committed={committed} present={bool(present)}")


def p5_a_killed_holder_leaves_no_stale_lock():
    banner("P5 — STALE: does a killed holder wedge every other worktree?")
    lock = control_root("stale") / "store.lock"
    holder_src = textwrap.dedent(f"""
        import fcntl, time
        h = open({str(lock)!r}, "a+")
        fcntl.flock(h.fileno(), fcntl.LOCK_EX)
        print("held", flush=True)
        time.sleep(300)
    """)
    proc = subprocess.Popen([sys.executable, "-c", holder_src], stdout=subprocess.PIPE, text=True)
    assert proc.stdout.readline().strip() == "held"

    def try_acquire() -> str:
        with open(lock, "a+") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                return "ACQUIRED"
            except OSError as exc:
                return f"refused ({errno.errorcode.get(exc.errno, exc.errno)})"

    print(f"  while the holder lives : {try_acquire()}")
    os.kill(proc.pid, signal.SIGKILL)
    proc.wait(timeout=30)
    time.sleep(0.2)
    print(f"  after SIGKILL          : {try_acquire()}")
    print(f"  lock file on disk      : {lock.exists()}")
    print("  => released by the KERNEL on process death. The file remaining is not a")
    print("     stale lock; there is no operator cleanup and no wedged worktree.")


if __name__ == "__main__":
    # docs/spikes/labs/<lab>/probe.py — four levels under the repo root, not three.
    default_src = Path(__file__).resolve().parents[4] / "src"
    src = sys.argv[1] if len(sys.argv) > 1 else str(default_src)
    if not Path(src).is_dir():
        raise SystemExit(f"cannot find the atdd source tree at {src}; pass it as argv[1]")
    report_target_store()
    p1_racing_proves_nothing()
    p2_the_window_loses_a_committed_write()
    p3_how_wide_is_the_window()
    p4_a_control_root_lock_closes_it(src)
    p5_a_killed_holder_leaves_no_stale_lock()
