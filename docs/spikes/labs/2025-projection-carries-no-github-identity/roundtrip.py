"""#2025 lab, probe 1 — the REAL round trip, through the file layer.

`measure.py` compared documents in memory. That is not the contract. The contract
is ``project(hydrate(committed)) == committed`` over BYTES ON DISK, and the thing
in between is a YAML serializer that has opinions about what a digit string is.

So this probe patches the two seams (`build_documents` grows the subtree,
`hydrate` merges and restores) and then runs the REAL `project`,
`projection_digest` and `check_canonicality` — the last of which hydrates into a
fresh in-memory store it migrates itself, exactly as CI would.

DESIGN-PHASE PROBE. This measures the behaviour of the projection spine BEFORE #2025
landed, plus the prototype fix that was proposed for it. The implementation has since
shipped, so what it reports is the historical finding, not the current state of the
code. The regression check for the shipped behaviour is the E003/C003 acceptances in
``src/atdd/state/tests/migrate_projection_authority/`` — ten of them, one per
acceptance, each building its own populated store.

Usage:  python roundtrip.py <control-root>
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

WORK_ITEM = "work_item"
GH, ISSUE = "github", "issue"

_real_build_documents = P.build_documents
_real_hydrate = P.hydrate


# --------------------------------------------------------------------------- #
# The two seams #2025 proposes to change, patched in so the REAL project(),
# projection_digest() and check_canonicality() exercise them end to end.
# --------------------------------------------------------------------------- #
def patched_build_documents(store: StateStore) -> dict[str, dict]:
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
            # str(), deliberately: the table column is TEXT, and a bare YAML
            # integer would come back an int and break the round trip. Probe 1c.
            document["external_refs"] = {GH: {ISSUE: str(issue_of[obj.uid])}}
        P.assert_deterministic(document, uid=obj.uid)
        P.validate_document(document)
        documents[obj.uid] = document
    return documents


def patched_hydrate(projection_dir: pathlib.Path, store: StateStore) -> P.HydrateResult:
    documents = P.read_projection(projection_dir)

    claimed: dict[str, str] = {}
    for uid in sorted(documents):
        issue = ((documents[uid].get("external_refs") or {}).get(GH) or {}).get(ISSUE)
        if issue is None:
            continue
        if str(issue) in claimed:
            raise P.ProjectionSchemaError(
                f"two documents claim github issue {issue}: {claimed[str(issue)]} and {uid}"
            )
        claimed[str(issue)] = uid

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
    return P.HydrateResult(hydrated=len(documents), uids=sorted(documents))


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

    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        work = pathlib.Path(tmp)
        conn = _migrated_copy(source, work / "copy.sqlite")
        store = StateStore(conn)

        # ---- 1a: BASELINE — the real pipeline, unpatched -------------------
        print("== 1a: baseline, today's projector (no external_refs) ==")
        base_dir = work / "baseline"
        P.project(store, base_dir)
        base = P.check_canonicality(base_dir)
        print(f"  {base.render().splitlines()[0]}")
        print(f"  digest: {P.projection_digest(base_dir)[:23]}…")
        if not base.ok:
            failures.append("baseline canonicality failed — the harness is wrong, not the change")

        # ---- 1b: the REAL round trip with the subtree populated ------------
        print("\n== 1b: with external_refs projected — REAL project + check_canonicality ==")
        P.build_documents = patched_build_documents
        P.hydrate = patched_hydrate
        try:
            out = work / "withrefs"
            result = P.project(store, out)
            carriers = sum(
                1 for path in result.files.values()
                if "external_refs:" in path.read_text(encoding="utf-8")
            )
            print(f"  files written: {len(result.files)}; carrying external_refs: {carriers}")

            sample = next(
                p for p in sorted(result.files.values())
                if "external_refs:" in p.read_text(encoding="utf-8")
            )
            text = sample.read_text(encoding="utf-8")
            snippet = "\n".join(
                line for line in text.splitlines()
                if line.startswith(("external_refs", "  github", "    issue"))
            )
            print(f"  as committed in {sample.name}:")
            for line in snippet.splitlines():
                print(f"    {line}")

            report = P.check_canonicality(out)
            print(f"  check_canonicality: {report.render().splitlines()[0]}")
            if not report.ok:
                failures.append("canonicality FAILED with external_refs populated")
                for mismatch in report.mismatches[:3]:
                    print(f"    ! {mismatch.filename}\n{mismatch.diff}")

            before_digest = P.projection_digest(out)
            again = work / "withrefs2"
            with P.MemoryStore() as mem:
                P.hydrate(out, mem)
                P.project(mem, again)
            after_digest = P.projection_digest(again)
            print(f"  digest stable across hydrate+re-project: {before_digest == after_digest}")
            if before_digest != after_digest:
                failures.append("projection digest moved across the round trip")

            # ---- 1c: would a bare YAML integer survive? --------------------
            print("\n== 1c: does the digit string survive YAML, or come back an int? ==")
            import yaml
            as_str = yaml.safe_load(P.canonical_bytes({"external_refs": {GH: {ISSUE: "1975"}}}))
            as_int = yaml.safe_load(P.canonical_bytes({"external_refs": {GH: {ISSUE: 1975}}}))
            str_v = as_str["external_refs"][GH][ISSUE]
            int_v = as_int["external_refs"][GH][ISSUE]
            print(f"  projected as str '1975' -> read back {str_v!r} ({type(str_v).__name__})")
            print(f"  projected as int  1975  -> read back {int_v!r} ({type(int_v).__name__})")
            print(f"  the two do NOT produce the same bytes: "
                  f"{P.canonical_bytes({'e': '1975'}) != P.canonical_bytes({'e': 1975})}")
            print("  => the contract must PIN the type, or a hand-edit that drops the quotes")
            print("     silently changes it and the round trip stops being byte-stable.")
        finally:
            P.build_documents = _real_build_documents
            P.hydrate = _real_hydrate

    print("\n" + "=" * 60)
    if failures:
        print("REFUTED / FAILURES:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("All round-trip hypotheses HELD.")
    return 0


if __name__ == "__main__":
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    raise SystemExit(main(root))
