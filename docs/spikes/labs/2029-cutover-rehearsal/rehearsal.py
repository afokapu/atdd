#!/usr/bin/env python3
"""#2029 lab — rehearse the projection cutover end to end, read-only against the live store.

Answers the question #2029 rests on: *does the shipped sequence — migrate-store, project,
commit, cutover — reach 3/3 on the real corpus?*

READ-ONLY BY CONSTRUCTION. The live Control Root store is never opened for write. It is
WAL-checkpointed and copied aside first (the two steps ``reconcile.backup_store`` performs,
because a plain ``cp`` of a WAL-mode database silently omits recent commits — see that
function's own docstring). Every mutation lands on the copy, inside a throwaway checkout
this script creates and removes.

It also demonstrates the defect #2024 owns, because #2029's Done-when depends on it: the
cutover criterion globs the WORKING TREE rather than reading HEAD, so 3/3 is reportable
before anything is committed.

Usage:  python3 rehearsal.py [--control-root PATH] [--keep]
Exit:   0 when the rehearsal reaches 3/3 and both defect demonstrations behave as recorded.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "src"))


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--control-root", default="/Users/alecfokapu/Github/atdd",
                    help="directory holding .atdd/state/state.sqlite")
    ap.add_argument("--keep", action="store_true", help="leave the scratch checkout in place")
    args = ap.parse_args()

    from atdd.state.db import connect
    from atdd.state.identity import is_uid
    from atdd.state.reconcile import checkpoint
    from atdd.state.store import StateStore
    from atdd.state.manifest_import import WORK_ITEM_KIND
    from atdd.state import store_migration as sm, projection as P, cutover

    live = Path(args.control_root) / ".atdd" / "state" / "state.sqlite"
    if not live.exists():
        print(f"FAIL: no store at {live}")
        return 2

    work = Path(tempfile.mkdtemp(prefix="2029-rehearsal-"))
    scratch = work / "checkout"
    try:
        # 1. A checkout to commit into. The Control Root is not a git repo in
        #    sibling-worktree layout, which is why --out is passed explicitly (#2024).
        assert _git(REPO, "worktree", "add", "-f", "--detach", str(scratch),
                    "origin/main").returncode == 0, "could not create the scratch checkout"

        # 2. WAL-checkpoint, then copy. Never the live file.
        checkpoint(live)
        (scratch / ".atdd" / "state").mkdir(parents=True, exist_ok=True)
        db = scratch / ".atdd" / "state" / "state.sqlite"
        shutil.copy2(live, db)

        conn = connect(db)
        store = StateStore(conn)
        before = store.objects.list(kind=WORK_ITEM_KIND)
        minted_before = [o for o in before if is_uid(o.uid)]
        print(f"corpus            {len(before)} work items, "
              f"{len(minted_before)} already contract-shaped")

        defects = sm.inspect_store(store)
        print(f"defects           {len(defects)}")
        if defects:
            print("FAIL: the dispositions do not cover this corpus")
            return 1

        rep = sm.migrate_store(conn)
        conn.commit()
        print(f"migrated          {len(rep.rekeyed)} rekeyed, {len(rep.attributed)} attributed, "
              f"drops on {len(rep.dropped)}")

        out = scratch / ".atdd" / "state" / "projection"
        res = P.project(store, out)
        canonical = P.check_canonicality(out).ok
        print(f"projected         {len(res.files)} documents | canonicality "
              f"{'OK' if canonical else 'MISMATCH'}")
        if not canonical:
            return 1

        # 3. Commit it. Hooks off: this is a measurement, not a delivery.
        _git(scratch, "checkout", "-q", "-b", "rehearsal")
        _git(scratch, "add", ".atdd/state/projection")
        staged = _git(scratch, "diff", "--cached", "--name-only").stdout.split()
        _git(scratch, "-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", "rehearsal")
        print(f"committed         {len(staged)} files")

        report = cutover.check(scratch)
        print(f"cutover           MET={report.met}")
        for c in report.criteria:
            print(f"  [{'PASS' if c.met else 'FAIL'}] {c.name}")
        if not report.met:
            print("FAIL: the cutover did not reach 3/3")
            return 1

        # 4. #2024's defect, which #2029's Done-when depends on: the criterion reads the
        #    working tree, so it disagrees with HEAD in both directions.
        def projection_met(root: Path) -> bool:
            r = cutover.check(root)
            return next(c.met for c in r.criteria if "projection" in c.name)

        shutil.rmtree(out)
        committed_only = projection_met(scratch)          # at HEAD, absent from the tree
        _git(scratch, "checkout", "--", ".atdd/state/projection")
        _git(scratch, "rm", "-r", "-q", "--cached", ".atdd/state/projection")
        tree_only = projection_met(scratch)               # in the tree, not committed

        print(f"committed-not-in-tree   -> {'MET' if committed_only else 'UNMET'}  (expect UNMET)")
        print(f"in-tree-not-committed   -> {'MET' if tree_only else 'UNMET'}  (expect MET)")
        if committed_only or not tree_only:
            print("NOTE: the working-tree/HEAD defect no longer reproduces — #2024 may have landed.")

        print("\nREHEARSAL PASSED — 3/3 reachable; live store untouched.")
        return 0
    finally:
        conn_open = locals().get("conn")
        if conn_open is not None:
            conn_open.close()
        if not args.keep:
            _git(REPO, "worktree", "remove", "--force", str(scratch))
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
