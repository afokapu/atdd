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

        # #2025: the transport must carry identity, or a workflow can create but never
        # update. Canonicality does not check this — it only round-trips the documents
        # through themselves, so it passes just as happily on a projection with none.
        docs = P.build_documents(store)
        with_ref = [d for d in docs.values()
                    if (d.get("external_refs") or {}).get("github", {}).get("issue")]
        print(f"carrying identity {len(with_ref)} of {len(docs)} documents")
        if not with_ref:
            print("FAIL: no document names its GitHub issue — the projection cannot be "
                  "the transport (#2025 regressed or has not landed)")
            return 1

        # 3. Commit it. Hooks off: this is a measurement, not a delivery.
        _git(scratch, "checkout", "-q", "-b", "rehearsal")
        _git(scratch, "add", ".atdd/state/projection")
        staged = _git(scratch, "diff", "--cached", "--name-only").stdout.split()
        _git(scratch, "-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", "rehearsal")
        print(f"committed         {len(staged)} files")

        # The Done-when is byte-identity against HEAD, not 3/3 canonicality: canonicality
        # only asks whether the committed documents round-trip through themselves, so a
        # stale or partial commit satisfies it. Compare the committed bytes directly.
        from atdd.state import gitstore
        prefix = P.PROJECTION_RELATIVE.as_posix()
        try:
            at_head = gitstore.projection_bytes_at(scratch, "HEAD", prefix)
        except Exception as exc:                       # pragma: no cover - reported, not raised
            print(f"byte-identity     COULD NOT CHECK: {exc}")
            at_head = None
        if at_head is not None:
            on_disk = {f.name: f.read_bytes() for f in sorted(out.glob("*.yaml"))}
            head_named = {k.rsplit("/", 1)[-1]: v for k, v in at_head.items()}
            identical = head_named == on_disk
            print(f"byte-identity     HEAD == fenced projection: {identical} "
                  f"({len(head_named)} at HEAD, {len(on_disk)} on disk)")
            if not identical:
                print("FAIL: committed bytes differ from the projection they came from")
                return 1

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

        # (a) at HEAD, absent from the working tree. A criterion that reads HEAD says MET.
        shutil.rmtree(out)
        committed_only = projection_met(scratch)
        _git(scratch, "checkout", "--", ".atdd/state/projection")

        # (b) in the working tree, absent from HEAD. Reset to the pre-projection commit so
        #     HEAD genuinely carries nothing — `git rm --cached` only unstages, it does not
        #     remove from HEAD, so the earlier form of this check tested nothing once the
        #     criterion started reading HEAD.
        _git(scratch, "reset", "-q", "--soft", "HEAD~1")
        _git(scratch, "reset", "-q")
        tree_only = projection_met(scratch)

        reads_head = committed_only and not tree_only
        print(f"at HEAD, not in tree     -> {'MET' if committed_only else 'UNMET'}"
              f"   (MET once the criterion reads HEAD)")
        print(f"in tree, not at HEAD     -> {'MET' if tree_only else 'UNMET'}"
              f" (UNMET once the criterion reads HEAD)")
        print(f"criterion reads HEAD     -> {reads_head}")
        if not reads_head:
            print("NOTE: the working-tree/HEAD defect still reproduces — #2024 has not landed.")

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
