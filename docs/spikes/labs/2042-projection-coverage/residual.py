"""#2042 lab, probe 1 — the residual, object by object, with a reason attached.

The issue quotes a 1,053 -> 748 gap and asks whether it is legitimate (filtered
kinds, archived phases) or a silent truncation. Prose cannot answer that; a
classification over every object can.

Every object in the store is assigned to exactly one bucket:

  projected                 it is in the projection
  excluded: kind=<k>        build_documents lists kind=work_item only
  excluded: phase=COMPLETE  ARCHIVED_PHASES — derived from merge-to-main
  UNEXPLAINED               it should have projected and did not

The last bucket is the finding. A residual of zero means the gap is fully
accounted for and the issue narrows to making the account executable; a non-zero
residual means objects are being dropped silently.

Usage:  python residual.py <control-root>
"""
from __future__ import annotations

import collections
import pathlib
import shutil
import sqlite3
import sys
import tempfile

from atdd.state import projection as P
from atdd.state import store_migration as SM
from atdd.state.store import StateStore


def classify(conn: sqlite3.Connection, store: StateStore) -> tuple[dict, list]:
    """Every stored object bucketed by why it is, or is not, in the projection."""
    documents = P.build_documents(store)
    projected = set(documents)
    buckets: collections.Counter = collections.Counter()
    residual: list[tuple[str, str, str]] = []

    for row in conn.execute("SELECT uid, kind, state FROM objects"):
        uid, kind, state = row["uid"], row["kind"], row["state"]
        if uid in projected:
            buckets["projected"] += 1
        elif kind != P.WORK_ITEM_KIND:
            buckets[f"excluded: kind={kind}"] += 1
        elif state in P.ARCHIVED_PHASES:
            buckets[f"excluded: phase={state}"] += 1
        else:
            buckets["UNEXPLAINED"] += 1
            residual.append((uid, kind, str(state)))
    return buckets, residual


def main(control_root: pathlib.Path) -> int:
    source = control_root / ".atdd" / "state" / "state.sqlite"
    if not source.is_file():
        print(f"no store at {source}", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory() as tmp:
        copy = pathlib.Path(tmp) / "copy.sqlite"
        shutil.copy(source, copy)
        conn = sqlite3.connect(copy)
        conn.row_factory = sqlite3.Row
        SM.migrate_store(conn)
        store = StateStore(conn)

        total = conn.execute("SELECT count(*) FROM objects").fetchone()[0]
        work_items = conn.execute(
            "SELECT count(*) FROM objects WHERE kind = ?", (P.WORK_ITEM_KIND,)
        ).fetchone()[0]
        buckets, residual = classify(conn, store)

        print(f"store objects      {total}")
        print(f"  of which work_item {work_items}")
        print(f"projected documents  {buckets['projected']}\n")
        for name, count in sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0])):
            print(f"  {name:<30} {count:>5}")
        accounted = sum(buckets.values())
        print(f"  {'TOTAL':<30} {accounted:>5}   (store holds {total})")

        print(f"\nRESIDUAL (unexplained): {len(residual)}")
        for entry in residual[:20]:
            print(f"    {entry}")
        if accounted != total:
            print("  !! the buckets do not sum to the store — the classification is wrong")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")))
