"""#2025 lab, probe 3 — what is ACTUALLY in external_refs, and what may be projected.

"Serialize the refs table" is not a design. This probe censuses every row —
every (provider, ref_kind), every key inside every row's `data` blob, every
object kind the rows point at — and then tests each candidate against the two
things that decide admissibility:

* ``assert_deterministic`` — would this content be refused at projection time?
* the #1622 dispositions — is this a key already ruled DROP, arriving under a
  new name?

DESIGN-PHASE PROBE. This measures the behaviour of the projection spine BEFORE #2025
landed, plus the prototype fix that was proposed for it. The implementation has since
shipped, so what it reports is the historical finding, not the current state of the
code. The regression check for the shipped behaviour is the E003/C003 acceptances in
``src/atdd/state/tests/migrate_projection_authority/`` — ten of them, one per
acceptance, each building its own populated store.

Usage:  python subtree.py <control-root>
"""
from __future__ import annotations

import collections
import json
import pathlib
import shutil
import sqlite3
import sys
import tempfile

from atdd.state import projection as P
from atdd.state import store_migration as SM
from atdd.state.store import StateStore

GH, ISSUE = "github", "issue"


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

        print("== census: every (provider, ref_kind), and the object kind it points at ==")
        rows = conn.execute(
            "SELECT r.provider, r.ref_kind, o.kind, count(*) n FROM external_refs r "
            "LEFT JOIN objects o ON o.uid = r.object_uid GROUP BY 1,2,3 ORDER BY n DESC"
        ).fetchall()
        total = 0
        for row in rows:
            total += row["n"]
            print(f"  {row['provider']:<8} {row['ref_kind']:<8} on {str(row['kind']):<14} {row['n']:>5}")
        print(f"  {'':<8} {'':<8} {'TOTAL':<17} {total:>5}")

        print("\n== every key that appears inside a row's `data` blob, by provider ==")
        keys: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
        for ref in store.external_refs.all():
            for key in (ref.data or {}):
                keys[f"{ref.provider}/{ref.ref_kind}"][key] += 1
        for slot in sorted(keys):
            for key, n in keys[slot].most_common():
                dropped = " <- #1622 ruled DROP" if key in SM.DROPPED_FROM_STORE else ""
                print(f"  {slot:<18} {key:<14} {n:>5}{dropped}")

        print("\n== admissibility: would each candidate survive assert_deterministic? ==")
        verdicts: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for ref in store.external_refs.all():
            slot = (ref.provider, ref.ref_kind)
            if slot in seen:
                continue
            seen.add(slot)

            # (a) the ref_value alone — what this issue proposes to project
            try:
                P.assert_deterministic(
                    {"external_refs": {ref.provider: {ref.ref_kind: str(ref.ref_value)}}}
                )
                value_ok = "clean"
            except P.NondeterministicProjectionError as exc:
                value_ok = f"REFUSED ({exc.reason})"

            # (b) the whole row, data blob included — the naive "just serialize it"
            try:
                P.assert_deterministic(
                    {"external_refs": {ref.provider: {ref.ref_kind: dict(ref.data or {})}}}
                )
                blob_ok = "clean"
            except P.NondeterministicProjectionError as exc:
                blob_ok = f"REFUSED at {exc.field_path} ({exc.reason})"
            verdicts.append((f"{ref.provider}/{ref.ref_kind}", f"ref_value={value_ok}; data blob={blob_ok}"))

        for slot, verdict in verdicts:
            print(f"  {slot:<18} {verdict}")

        print("\n== the ruling: which projected rows would readmit a DROPPED key ==")
        for key in sorted(SM.DROPPED_FROM_STORE):
            n = conn.execute(
                "SELECT count(*) FROM external_refs WHERE provider=? AND ref_kind=? "
                f"AND json_extract(data,'$.{key}') IS NOT NULL", (GH, ISSUE),
            ).fetchone()[0]
            if n:
                gh = conn.execute(
                    "SELECT count(*) FROM external_refs WHERE provider=? AND ref_kind=?",
                    (GH, ISSUE),
                ).fetchone()[0]
                print(f"  data.{key}: {n} of {gh} (github, issue) rows"
                      f"  -> carrying the blob would reverse #1622 by the back door")

        print("\n== shape of what IS admitted ==")
        gh_rows = [r for r in store.external_refs.all() if r.provider == GH and r.ref_kind == ISSUE]
        nondigit = [r for r in gh_rows if not str(r.ref_value).isdigit()]
        per_object = collections.Counter(r.object_uid for r in gh_rows)
        multi = [uid for uid, n in per_object.items() if n > 1]
        kinds = collections.Counter(
            (store.objects.get(r.object_uid).kind if store.objects.get(r.object_uid) else None)
            for r in gh_rows
        )
        print(f"  (github, issue) rows:            {len(gh_rows)}")
        print(f"  non-digit ref_values:            {len(nondigit)}")
        print(f"  objects carrying more than one:  {len(multi)}   (so the mapping is 1:1)")
        print(f"  by object kind:                  {dict(kinds)}")
        projectable = {
            o.uid for o in store.objects.list(kind="work_item") if o.state not in P.ARCHIVED_PHASES
        }
        on_projected = len({r.object_uid for r in gh_rows} & projectable)
        print(f"  on a PROJECTED work item:        {on_projected}")
        print(f"  on an ARCHIVED (COMPLETE) one:   "
              f"{kinds.get('work_item', 0) - on_projected}"
              "   <- hydrate must NOT delete these")
    return 0


if __name__ == "__main__":
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    raise SystemExit(main(root))
