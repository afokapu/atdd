"""#2025 lab, probe 6 — the two gaps re-review left open.

6a  A legal bot value is `{"github": {"pr": "2028"}}` while the TABLE contributes
    `github.issue`. The earlier acceptance only exercised a NON-github provider,
    so it would pass even if the whole `github` subtree were replaced. Does
    `github.pr` survive a round trip?

6b  The refs table is UNIQUE (provider, ref_kind, ref_value) — NOT per object
    (migrations.py:74). Two distinct GitHub issue refs on ONE uid is therefore
    representable today. A single scalar `github.issue` cannot carry it. What
    does the proposed design do?

DESIGN-PHASE PROBE. This measures the behaviour of the projection spine BEFORE #2025
landed, plus the prototype fix that was proposed for it. The implementation has since
shipped, so what it reports is the historical finding, not the current state of the
code. The regression check for the shipped behaviour is the E003/C003 acceptances in
``src/atdd/state/tests/migrate_projection_authority/`` — ten of them, one per
acceptance, each building its own populated store.

Usage:  python rr2.py <control-root>
"""
from __future__ import annotations

import json
import pathlib
import shutil
import sqlite3
import sys
import tempfile

from atdd.state import projection as P
from atdd.state import store_migration as SM
from atdd.state.store import StateStore

from roundtrip import patched_build_documents, patched_hydrate

GH, ISSUE, PR = "github", "issue", "pr"
WORK_ITEM = "work_item"


def _migrated_copy(source: pathlib.Path, dest: pathlib.Path) -> sqlite3.Connection:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(source, dest)
    conn = sqlite3.connect(dest)
    conn.row_factory = sqlite3.Row
    SM.migrate_store(conn)
    return conn


def main(control_root: pathlib.Path) -> int:
    source = control_root / ".atdd" / "state" / "state.sqlite"
    if not source.is_file():
        print(f"no store at {source}", file=sys.stderr)
        return 2

    gaps: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        work = pathlib.Path(tmp)
        conn = _migrated_copy(source, work / "copy.sqlite")
        store = StateStore(conn)

        row = conn.execute(
            "SELECT r.object_uid, r.ref_value FROM external_refs r JOIN objects o ON o.uid=r.object_uid "
            "WHERE r.provider=? AND r.ref_kind=? AND o.kind=? AND o.state<>'COMPLETE' LIMIT 1",
            (GH, ISSUE, WORK_ITEM),
        ).fetchone()
        uid, issue_no = row["object_uid"], row["ref_value"]

        # ---- 6a: a second ref KIND under the same provider -------------------
        print("== 6a: does github.pr survive, when the table only sources github.issue? ==")
        obj = store.objects.get(uid)
        data = dict(obj.data)
        data["external_refs"] = {GH: {PR: "2028"}, "jira": {"ticket": "ATDD-17"}}
        store.objects.upsert(uid, WORK_ITEM, state=obj.state, data=data)
        print(f"  bot wrote:  {{'github': {{'pr': '2028'}}, 'jira': {{'ticket': 'ATDD-17'}}}}")
        print(f"  table holds: github.issue = {issue_no}")

        document = patched_build_documents(store)[uid]
        refs = document.get("external_refs") or {}
        print(f"  projector emits: {refs!r}")
        gh_sub = refs.get(GH) or {}
        pr_survived = gh_sub.get(PR) == "2028"
        jira_survived = (refs.get("jira") or {}).get("ticket") == "ATDD-17"
        issue_present = gh_sub.get(ISSUE) == str(issue_no)
        print(f"  github.pr survived:   {pr_survived}")
        print(f"  jira.ticket survived: {jira_survived}")
        print(f"  github.issue present: {issue_present}")
        if not pr_survived:
            print("  => github.pr DESTROYED. The earlier acceptance used a non-github provider")
            print("     only, so it would pass while this silently fails. The merge must be at")
            print("     the (provider, ref_kind) LEAF, not at the provider.")
            gaps.append("6a: a same-provider second ref kind (github.pr) is destroyed at projection")

        # ---- 6b: two distinct issue refs on ONE object -----------------------
        print("\n== 6b: two distinct github issue refs on one uid ==")
        conn2 = _migrated_copy(source, work / "second" / "copy.sqlite")
        store2 = StateStore(conn2)
        row2 = conn2.execute(
            "SELECT r.object_uid, r.ref_value FROM external_refs r JOIN objects o ON o.uid=r.object_uid "
            "WHERE r.provider=? AND r.ref_kind=? AND o.kind=? AND o.state<>'COMPLETE' LIMIT 1",
            (GH, ISSUE, WORK_ITEM),
        ).fetchone()
        uid2, first = row2["object_uid"], row2["ref_value"]
        second = str(int(first) + 100000)
        store2.external_refs.link(uid2, GH, ISSUE, second)
        held = conn2.execute(
            "SELECT ref_value FROM external_refs WHERE object_uid=? AND provider=? AND ref_kind=? "
            "ORDER BY ref_value", (uid2, GH, ISSUE),
        ).fetchall()
        values = [r[0] for r in held]
        print(f"  the store now binds {uid2} to issues {values}")
        print(f"  representable: {len(values) > 1}  (UNIQUE is on (provider, ref_kind, ref_value),")
        print(f"                  not on (object_uid, provider, ref_kind) — migrations.py:74)")

        doc2 = patched_build_documents(store2)[uid2]
        emitted = ((doc2.get("external_refs") or {}).get(GH) or {}).get(ISSUE)
        print(f"  the projector emits github.issue = {emitted!r}")
        print(f"  the other {len(values) - 1} ref(s) are: {[v for v in values if v != emitted]}")
        if len(values) > 1 and emitted is not None:
            print("  => SILENTLY DROPPED, and which one survives depends on dict iteration order")
            print("     over store.external_refs.all(). A scalar cannot carry this state, so the")
            print("     design must REFUSE it before any write — or enforce one-issue-per-object.")
            gaps.append("6b: a second github issue ref on one object is silently dropped, not refused")

    print("\n" + "=" * 60)
    print(f"GAPS CONFIRMED: {len(gaps)}")
    for gap in gaps:
        print(f"  - {gap}")
    return 0


if __name__ == "__main__":
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    raise SystemExit(main(root))
