"""#2025 lab — what the projection carries, and what hydrate deletes.

Read-only with respect to the live store: every measurement runs against a COPY.
`store_migration.migrate_store()` is applied to the copy first, so the numbers
describe the world the projection cutover is about to create.

Usage:  python measure.py <control-root>
"""
from __future__ import annotations

import os
import pathlib
import shutil
import sqlite3
import sys
import tempfile

from atdd.state import projection as P
from atdd.state import store_migration as SM
from atdd.state.migrations import CORE_MIGRATIONS
from atdd.state.store import StateStore

WORK_ITEM = "work_item"
GH, ISSUE = "github", "issue"
#: The keys whose survival across a hydrate is the whole question.
WATCHED = ("feature", "branch", "created", "id", "worktree")


def _carriers(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        key: conn.execute(
            f"SELECT count(*) FROM objects WHERE kind='{WORK_ITEM}' "
            f"AND json_extract(data,'$.{key}') IS NOT NULL"
        ).fetchone()[0]
        for key in WATCHED
    }


def _refs(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT count(*) FROM external_refs").fetchone()[0]


def _open_migrated(source: pathlib.Path, workdir: pathlib.Path) -> sqlite3.Connection:
    """A migrated COPY of the live store. The original is never opened for write."""
    workdir.mkdir(parents=True, exist_ok=True)
    copy = workdir / "copy.sqlite"
    shutil.copy(source, copy)
    conn = sqlite3.connect(copy)
    conn.row_factory = sqlite3.Row
    SM.migrate_store(conn)
    return conn


# --------------------------------------------------------------------------- #
# The prototype: the two changes #2025 proposes, in the smallest form that can
# be measured. Not the implementation — RED owns that.
# --------------------------------------------------------------------------- #
def build_documents_v2(store: StateStore) -> dict[str, dict]:
    """`build_documents`, plus the `(github, issue)` subtree folded in.

    The refs table is grouped ONCE for the whole run rather than queried per
    object, and only the `ref_value` crosses over — never the row's `data` blob.
    """
    issue_of = {
        ref.object_uid: ref.ref_value
        for ref in store.external_refs.all()
        if ref.provider == GH and ref.ref_kind == ISSUE
    }
    documents: dict[str, dict] = {}
    for obj in store.objects.list(kind=WORK_ITEM):
        if obj.state in P.ARCHIVED_PHASES:
            continue
        document = {k: v for k, v in obj.data.items() if k not in P.STRIPPED_AT_PROJECTION}
        document["uid"] = obj.uid
        document["phase"] = obj.state
        document.setdefault("state", P.STATE_ACTIVE)
        document.pop("external_refs", None)
        if obj.uid in issue_of:
            document["external_refs"] = {GH: {ISSUE: issue_of[obj.uid]}}
        P.assert_deterministic(document, uid=obj.uid)
        P.validate_document(document)
        documents[obj.uid] = document
    return documents


def hydrate_v2(documents: dict[str, dict], store: StateStore) -> None:
    """`hydrate`, as a field-scoped merge that also restores the refs table.

    Two departures from today's `hydrate`, both measured below:

    - The object write preserves `STRIPPED_AT_PROJECTION` from the object already
      in the store. A document that omits `branch` is not claiming the object has
      no branch; it is declining to have an opinion, and a wholesale replace turns
      that silence into a deletion.
    - The `(github, issue)` slice of the refs table is restored. Rows the
      projection does not name are left alone — 304 of them belong to `COMPLETE`
      objects the projection deliberately archives out.

    Uniqueness is checked across the whole set BEFORE the first write, matching
    `build_documents`' refuse-before-any-write discipline: `link` resolves a
    collision last-writer-wins, which would silently re-point a live binding.
    """
    claimed: dict[str, str] = {}
    for uid in sorted(documents):
        issue = ((documents[uid].get("external_refs") or {}).get(GH) or {}).get(ISSUE)
        if issue is None:
            continue
        if issue in claimed:
            raise P.ProjectionSchemaError(
                f"two documents claim github issue {issue}: {claimed[issue]} and {uid}"
            )
        claimed[issue] = uid

    for uid in sorted(documents):
        obj_uid, phase, data = P.document_to_object(documents[uid])
        existing = store.objects.get(obj_uid)
        if existing is not None:
            for key in P.STRIPPED_AT_PROJECTION:
                if key in existing.data:
                    data[key] = existing.data[key]
        store.objects.upsert(obj_uid, WORK_ITEM, state=phase, data=data)
        issue = ((documents[uid].get("external_refs") or {}).get(GH) or {}).get(ISSUE)
        if issue is not None:
            store.external_refs.link(obj_uid, GH, ISSUE, str(issue))


def _fresh_store(path: pathlib.Path) -> tuple[sqlite3.Connection, StateStore]:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    for migration in CORE_MIGRATIONS:
        conn.executescript(migration.sql)
    conn.commit()
    return conn, StateStore(conn)


def main(control_root: pathlib.Path) -> int:
    source = control_root / ".atdd" / "state" / "state.sqlite"
    if not source.is_file():
        print(f"no store at {source}", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory() as tmp:
        work = pathlib.Path(tmp)
        conn = _open_migrated(source, work)
        store = StateStore(conn)

        print("== claim 1: the projection carries no GitHub identity ==")
        today = P.build_documents(store)
        print(f"  projectable documents:              {len(today)}")
        print(f"  …carrying any external_refs key:    "
              f"{sum(1 for d in today.values() if 'external_refs' in d)}")
        total = _refs(conn)
        gh_rows = conn.execute(
            "SELECT count(*) FROM external_refs WHERE provider=? AND ref_kind=?", (GH, ISSUE)
        ).fetchone()[0]
        on_projected = len(set(today) & {
            row[0] for row in conn.execute(
                "SELECT DISTINCT object_uid FROM external_refs WHERE provider=? AND ref_kind=?",
                (GH, ISSUE),
            )
        })
        print(f"  (github, issue) rows in the table:  {gh_rows} of {total}")
        print(f"  …pointing at a projected uid:       {on_projected}")

        print("\n== claim 2: a wholesale table serialization is REFUSED, not merely leaky ==")
        for ref in store.external_refs.all():
            if ref.provider == GH and ref.ref_kind == ISSUE:
                continue
            try:
                P.assert_deterministic({"external_refs": {ref.provider: ref.data}}, uid=ref.object_uid)
            except P.NondeterministicProjectionError as exc:
                print(f"  first non-projected row refuses the whole corpus: {exc}")
                break
        else:
            print("  no non-projected row carries a determinism leak")
        recovery = conn.execute(
            "SELECT count(*) FROM external_refs WHERE provider=? AND ref_kind=? "
            "AND json_extract(data,'$._recovery') IS NOT NULL", (GH, ISSUE),
        ).fetchone()[0]
        print(f"  (github, issue) rows carrying a dropped _recovery bag: {recovery} of {gh_rows}")

        print("\n== claim 3: merge-hydrate loses nothing and keeps the round trip ==")
        documents = build_documents_v2(store)
        print(f"  documents naming their github issue: "
              f"{sum(1 for d in documents.values() if d.get('external_refs'))} of {len(documents)}")
        print(f"  before hydrate: {_carriers(conn)}  refs: {_refs(conn)}")
        hydrate_v2(documents, store)
        print(f"  after  hydrate: {_carriers(conn)}  refs: {_refs(conn)}")
        again = build_documents_v2(store)
        identical = set(again) == set(documents) and all(
            P.canonical_bytes(again[uid]) == P.canonical_bytes(documents[uid]) for uid in documents
        )
        print(f"  project(hydrate(p)) == p, byte-for-byte: {identical}")

        print("\n== the inbound case: hydrate into a FRESH, empty store ==")
        peer_conn, peer = _fresh_store(work / "peer.sqlite")
        hydrate_v2(documents, peer)
        print(f"  objects:            {peer_conn.execute('SELECT count(*) FROM objects').fetchone()[0]}")
        print(f"  external_refs rows: {_refs(peer_conn)}   (today's hydrate: 0)")
        sample = next(iter(sorted(
            ((d.get('external_refs') or {}).get(GH) or {}).get(ISSUE)
            for d in documents.values() if d.get('external_refs')
        )))
        resolved = peer.external_refs.resolve(GH, ISSUE, sample)
        obj = peer.objects.get(resolved.object_uid) if resolved else None
        print(f"  resolve({GH}, {ISSUE}, {sample}) -> {resolved.object_uid if resolved else None}")
        print(f"    its branch: {obj.data.get('branch') if obj else None} | "
              f"its feature: {obj.data.get('feature') if obj else None}")

        print("\n== for contrast: today's wholesale-replace hydrate ==")
        conn2 = _open_migrated(source, work / "second")
        store2 = StateStore(conn2)
        before = _carriers(conn2)
        out = work / "projection"
        P.project(store2, out)
        P.hydrate(out, store2)
        after = _carriers(conn2)
        print(f"  before: {before}")
        print(f"  after:  {after}")
        print(f"  lost:   { {k: before[k] - after[k] for k in WATCHED} }")
    return 0


if __name__ == "__main__":
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else os.getcwd())
    raise SystemExit(main(root))
