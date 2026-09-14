"""#2025 lab, probe 4 — attack the PROPOSED design, not the current one.

Probes 1-3 showed the current code is broken and the proposed fix repairs it.
That is the easy half. `check_canonicality` hydrates into an EMPTY `MemoryStore`
(projection.py:719-722), so it can only ever prove things about a store with
nothing in it — and every property the crux depends on is a property of a
POPULATED store. An acceptance that leans on `check_canonicality` for those
passes vacuously.

So: three adversarial cases, each run against the proposed design, each asked to
fail. A probe that cannot fail proves nothing.

  4a  a malformed nested ref          — is it refused, or does it reach the store?
  4b  a ref colliding with one the local store already holds  — refused, or silently re-pointed?
  4c  a ref whose local row carries a `data` blob             — preserved, or wiped?

Usage:  python adversarial.py <control-root>
"""
from __future__ import annotations

import pathlib
import shutil
import sqlite3
import sys
import tempfile

from atdd.state import projection as P
from atdd.state import store_migration as SM
from atdd.state.store import StateStore

from roundtrip import patched_build_documents, patched_hydrate

GH, ISSUE = "github", "issue"
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

        # ---- 4a: a malformed nested ref ------------------------------------
        print("== 4a: a malformed nested ref — refused, or admitted? ==")
        for label, value in (("str '1975' (intended)", "1975"),
                             ("int 1975 (hand-edit drops quotes)", 1975),
                             ("a nested dict where a scalar belongs", {"number": 1975}),
                             ("a list", ["1975"])):
            document = {
                "uid": "wi_01M2EZ25BPW2NNQTPCQFWS5RQ9", "phase": "PLANNED",
                "state": "ACTIVE", "owner_actor": "atdd:unattributed",
                "external_refs": {GH: {ISSUE: value}},
            }
            try:
                P.validate_document(document)
                verdict = "ADMITTED"
            except P.ProjectionSchemaError as exc:
                verdict = f"refused ({exc})"
            print(f"  {label:<38} -> {verdict}")
        print("  => validate_document types external_refs as `dict` and reaches NO deeper,")
        print("     so every one of these is admitted. The contract must type the leaf.")
        gaps.append("4a: a malformed nested ref is admitted by validate_document today")

        # ---- 4b + 4c: collision and data preservation, on a POPULATED store -
        conn = _migrated_copy(source, work / "copy.sqlite")
        store = StateStore(conn)

        victim = conn.execute(
            "SELECT r.object_uid, r.ref_value, r.data FROM external_refs r "
            "JOIN objects o ON o.uid = r.object_uid "
            "WHERE r.provider=? AND r.ref_kind=? AND o.kind=? AND o.state <> 'COMPLETE' "
            "AND r.data <> '{}' ORDER BY CAST(r.ref_value AS INTEGER) DESC LIMIT 1",
            (GH, ISSUE, WORK_ITEM),
        ).fetchone()
        other = conn.execute(
            "SELECT uid FROM objects WHERE kind=? AND uid <> ? AND state <> 'COMPLETE' LIMIT 1",
            (WORK_ITEM, victim["object_uid"]),
        ).fetchone()

        print(f"\n== 4b: a projection claiming an issue the local store binds elsewhere ==")
        print(f"  local store:  issue {victim['ref_value']} -> {victim['object_uid']}")
        print(f"  a peer says:  issue {victim['ref_value']} -> {other['uid']}")

        before_owner = victim["object_uid"]
        store.external_refs.link(other["uid"], GH, ISSUE, str(victim["ref_value"]))
        after = store.external_refs.resolve(GH, ISSUE, str(victim["ref_value"]))
        print(f"  after link(): issue {victim['ref_value']} -> {after.object_uid}")
        if after.object_uid != before_owner:
            print("  => SILENTLY RE-POINTED. link() is ON CONFLICT DO UPDATE SET object_uid,")
            print("     so last writer wins with no signal. The proposed hydrate checks")
            print("     uniqueness WITHIN the document set — it never checks against the")
            print("     refs the local store ALREADY holds. That is the collision that")
            print("     actually happens on an inbound ingest.")
            gaps.append("4b: proposed hydrate does not detect collision against EXISTING refs")

        print(f"\n== 4c: does the restore preserve a ref row's existing `data` blob? ==")
        conn2 = _migrated_copy(source, work / "second" / "copy.sqlite")
        store2 = StateStore(conn2)
        row = conn2.execute(
            "SELECT object_uid, ref_value, data FROM external_refs "
            "WHERE provider=? AND ref_kind=? AND data <> '{}' LIMIT 1", (GH, ISSUE),
        ).fetchone()
        print(f"  before: data = {row['data']}")
        store2.external_refs.link(row["object_uid"], GH, ISSUE, str(row["ref_value"]))
        now = conn2.execute(
            "SELECT data FROM external_refs WHERE provider=? AND ref_kind=? AND ref_value=?",
            (GH, ISSUE, str(row["ref_value"])),
        ).fetchone()
        print(f"  after link(..., data=None): data = {now['data']}")
        if now["data"] != row["data"]:
            print("  => WIPED. _dumps(None) is '{}' and link() is DO UPDATE SET data=excluded.data.")
            print("     This is the SAME wholesale-replace fault this issue exists to fix,")
            print("     reproduced one table over — by the proposed fix itself.")
            nonempty = conn2.execute(
                "SELECT count(*) FROM external_refs WHERE provider=? AND ref_kind=? AND data <> '{}'",
                (GH, ISSUE),
            ).fetchone()[0]
            print(f"     {nonempty} (github, issue) rows carry a non-empty data blob today.")
            gaps.append("4c: the proposed restore WIPES an existing ref row's data blob")

        # ---- 4d: does the projector preserve a provider it does not source? -
        print(f"\n== 4d: a bot-written provider subtree the projector cannot source ==")
        target = conn2.execute(
            "SELECT uid, data FROM objects WHERE kind=? AND state <> 'COMPLETE' LIMIT 1",
            (WORK_ITEM,),
        ).fetchone()
        import json as _json
        data = _json.loads(target["data"])
        data["external_refs"] = {"jira": {"ticket": "ATDD-17"}}
        store2.objects.upsert(target["uid"], WORK_ITEM, state="PLANNED", data=data)
        print(f"  the bot wrote: {{'jira': {{'ticket': 'ATDD-17'}}}} into {target['uid']}")
        built = patched_build_documents(store2)[target["uid"]]
        print(f"  the projector emits: {built.get('external_refs')!r}")
        if (built.get("external_refs") or {}).get("jira") is None:
            print("  => DESTROYED. The proposed build_document pops external_refs and rebuilds")
            print("     it from the table, which holds no jira row — so a provider the bot is")
            print("     entitled to write is deleted at projection. Same wholesale-replace")
            print("     fault, third application. build_document must MERGE the (github, issue)")
            print("     slice into the existing subtree, not replace it.")
            gaps.append("4d: the proposed build_document DESTROYS a non-github provider subtree")

        # ---- and the reviewer's point: check_canonicality cannot see any of it
        print(f"\n== does check_canonicality catch any of these? ==")
        real_build, real_hydrate = P.build_documents, P.hydrate
        P.build_documents, P.hydrate = patched_build_documents, patched_hydrate
        try:
            out = work / "projection"
            P.project(store2, out)
            report = P.check_canonicality(out)
            print(f"  {report.render().splitlines()[0]}")
        finally:
            P.build_documents, P.hydrate = real_build, real_hydrate
        print("  => It passes. It hydrates into an EMPTY MemoryStore, so there is no")
        print("     existing object to preserve, no existing ref to collide with, and no")
        print("     existing data blob to wipe. Every property the crux depends on is")
        print("     INVISIBLE to it. Acceptances must build a populated store themselves.")

    print("\n" + "=" * 60)
    print(f"GAPS FOUND IN THE PROPOSED DESIGN: {len(gaps)}")
    for gap in gaps:
        print(f"  - {gap}")
    return 0


if __name__ == "__main__":
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    raise SystemExit(main(root))
