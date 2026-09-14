"""#2025 lab, probe 2 — the wholesale-replace hazard, measured at the GATE.

`ObjectStore.upsert` is ``data=excluded.data`` and `hydrate` calls it per object.
Counting the data keys that disappear understates the finding, because a key is
only worth anything to the caller that reads it. So this probe drives the two
REAL gate resolvers across a hydrate and reports what each one answers before and
after:

* ``coach.gate.approval_binding._branch_in_store`` — the pre-commit registration
  gate's issue -> branch resolver.
* ``coach.commands.issue_feature_binding._work_item_for_issue`` — the resolver
  behind the smoke-obligation gate's issue -> feature URN read.

Both enter through ``external_refs.resolve(github, issue, N)``, which is the other
half of why this issue exists: on a store hydrated from the projection today, that
table is empty and both answer nothing regardless of what the data bag holds.

DESIGN-PHASE PROBE. This measures the behaviour of the projection spine BEFORE #2025
landed, plus the prototype fix that was proposed for it. The implementation has since
shipped, so what it reports is the historical finding, not the current state of the
code. The regression check for the shipped behaviour is the E003/C003 acceptances in
``src/atdd/state/tests/migrate_projection_authority/`` — ten of them, one per
acceptance, each building its own populated store.

Usage:  python hazard.py <control-root>
"""
from __future__ import annotations

import pathlib
import shutil
import sqlite3
import sys
import tempfile

from atdd.coach.commands.issue_feature_binding import _work_item_for_issue
from atdd.coach.gate.approval_binding import _branch_in_store
from atdd.state import projection as P
from atdd.state import store_migration as SM
from atdd.state.store import StateStore

from roundtrip import patched_build_documents, patched_hydrate

WORK_ITEM = "work_item"
GH, ISSUE = "github", "issue"
WATCHED = ("feature", "branch", "created", "id", "worktree")
SAMPLE_SIZE = 200


def _carriers(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        key: conn.execute(
            f"SELECT count(*) FROM objects WHERE kind='{WORK_ITEM}' "
            f"AND json_extract(data,'$.{key}') IS NOT NULL"
        ).fetchone()[0]
        for key in WATCHED
    }


def _migrated_copy(source: pathlib.Path, dest: pathlib.Path) -> sqlite3.Connection:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(source, dest)
    conn = sqlite3.connect(dest)
    conn.row_factory = sqlite3.Row
    SM.migrate_store(conn)
    return conn


def _gate_answers(store: StateStore, issues: list[str]) -> tuple[int, int]:
    """How many of *issues* each real gate resolver can still answer."""
    branches = 0
    features = 0
    for number in issues:
        _uid, branch = _branch_in_store(store, int(number))
        if branch:
            branches += 1
        obj = _work_item_for_issue(store, int(number))
        if obj is not None and obj.data.get("feature"):
            features += 1
    return branches, features


def main(control_root: pathlib.Path) -> int:
    source = control_root / ".atdd" / "state" / "state.sqlite"
    if not source.is_file():
        print(f"no store at {source}", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory() as tmp:
        work = pathlib.Path(tmp)
        conn = _migrated_copy(source, work / "copy.sqlite")
        store = StateStore(conn)

        # A sample of issues that are ANSWERABLE today: the gate resolvers can
        # name both a branch and a feature for them. Measuring on issues that
        # were already unanswerable would flatter the result.
        rows = conn.execute(
            "SELECT r.ref_value FROM external_refs r JOIN objects o ON o.uid = r.object_uid "
            "WHERE r.provider=? AND r.ref_kind=? AND o.kind=? "
            "AND json_extract(o.data,'$.branch') IS NOT NULL "
            "AND json_extract(o.data,'$.feature') IS NOT NULL "
            "AND o.state <> 'COMPLETE' ORDER BY CAST(r.ref_value AS INTEGER) DESC LIMIT ?",
            (GH, ISSUE, WORK_ITEM, SAMPLE_SIZE),
        ).fetchall()
        issues = [row[0] for row in rows]
        print(f"sample: {len(issues)} live issues the gates can fully answer today")

        before_keys = _carriers(conn)
        before_branch, before_feature = _gate_answers(store, issues)
        print(f"\nBEFORE hydrate")
        print(f"  data keys:                        {before_keys}")
        print(f"  registration gate resolves branch: {before_branch}/{len(issues)}")
        print(f"  smoke-obligation gate resolves feature: {before_feature}/{len(issues)}")

        out = work / "projection"
        P.project(store, out)
        P.hydrate(out, store)

        after_keys = _carriers(conn)
        after_branch, after_feature = _gate_answers(store, issues)
        print(f"\nAFTER one project+hydrate cycle (today's wholesale replace)")
        print(f"  data keys:                        {after_keys}")
        print(f"  registration gate resolves branch: {after_branch}/{len(issues)}")
        print(f"  smoke-obligation gate resolves feature: {after_feature}/{len(issues)}")
        print(f"\n  lost: { {k: before_keys[k] - after_keys[k] for k in WATCHED} }")

        # ---- and now the PROPOSED fix, at the same gate level --------------
        conn2 = _migrated_copy(source, work / "fixed" / "copy.sqlite")
        store2 = StateStore(conn2)
        fixed_before_keys = _carriers(conn2)
        fixed_before_branch, fixed_before_feature = _gate_answers(store2, issues)

        real_build, real_hydrate = P.build_documents, P.hydrate
        P.build_documents, P.hydrate = patched_build_documents, patched_hydrate
        try:
            out2 = work / "fixed-projection"
            P.project(store2, out2)
            P.hydrate(out2, store2)
        finally:
            P.build_documents, P.hydrate = real_build, real_hydrate

        fixed_keys = _carriers(conn2)
        fixed_branch, fixed_feature = _gate_answers(store2, issues)
        print(f"\nAFTER one cycle with the PROPOSED merge-hydrate + refs restore")
        print(f"  data keys:                        {fixed_keys}")
        print(f"  registration gate resolves branch: {fixed_branch}/{len(issues)}")
        print(f"  smoke-obligation gate resolves feature: {fixed_feature}/{len(issues)}")
        print(f"  lost: { {k: fixed_before_keys[k] - fixed_keys[k] for k in WATCHED} }")

        repaired = (
            fixed_branch == fixed_before_branch == len(issues)
            and fixed_feature == fixed_before_feature == len(issues)
            and fixed_keys == fixed_before_keys
        )

        destroyed = (after_branch < before_branch) or (after_feature < before_feature)
        print("\n" + "=" * 60)
        if destroyed:
            print("HYPOTHESIS HELD — the hazard is REAL and reaches the gates:")
            print(f"  branch resolution:  {before_branch} -> {after_branch}")
            print(f"  feature resolution: {before_feature} -> {after_feature}")
            print("  Both gates enter through external_refs.resolve(github, issue, N),")
            print("  which still answers here only because this store already HELD the")
            print("  refs. On a store hydrated from the projection alone the table is")
            print("  empty and both answer nothing at all.")
        else:
            print("THE HAZARD IS GONE from the shipped hydrate — both gates still answer after")
            print("a real project+hydrate cycle. That is the POST-FIX reading: this probe was")
            print("written against the pre-#2025 spine, where the same run took both gates from")
            print(f"{before_branch}/{len(issues)} to 0/{len(issues)}. Nothing to re-examine; the")
            print("regression check is the C003 acceptances, not this file.")

        if repaired:
            print("\nAND THE PROPOSED FIX HOLDS — merge-hydrate + refs restore:")
            print(f"  branch resolution:  {fixed_before_branch} -> {fixed_branch} (no loss)")
            print(f"  feature resolution: {fixed_before_feature} -> {fixed_feature} (no loss)")
            print("  No stripped key was deleted, and both gates still answer.")
        else:
            print("\nTHE PROPOSED FIX DOES NOT HOLD — rescope before RED.")
        # Either reading is a pass: the hazard is present (pre-fix) and the prototype
        # repairs it, or the shipped code no longer exhibits it at all.
        return 0 if repaired else 1


if __name__ == "__main__":
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    raise SystemExit(main(root))
