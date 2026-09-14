# Lab — #2025: the committed projection carries no GitHub identity

Three hypotheses, each stated so it could be false, each with its own probe.

| probe | hypothesis | verdict |
|---|---|---|
| `roundtrip.py` | a projection carrying `external_refs` still satisfies `project(hydrate(p)) == p` byte-for-byte and passes `check_canonicality` | **HELD** — and surfaced the str/int contract gap |
| `hazard.py` | today's wholesale-replace `hydrate` destroys `feature` and `branch`, and the destruction reaches the gates that read them | **HELD** — 174/174 → 0/0 on both gates; the proposed merge restores 174/174 |
| `subtree.py` | the refs table cannot be serialized wholesale, and every excluded row has a stateable reason | **HELD** — three independent exclusion grounds |

## Running them

    ./lab.sh                 # the corpus census + the hazard, end to end
    PYTHONPATH=../../../../src python3 roundtrip.py <control-root>
    PYTHONPATH=../../../../src:. python3 hazard.py  <control-root>
    PYTHONPATH=../../../../src python3 subtree.py   <control-root>

All four are **read-only** with respect to the live store: every measurement runs
against a copy, and `store_migration.migrate_store()` is applied to the copy first,
so the numbers describe the world the projection cutover is about to create rather
than the pre-migration one.

`roundtrip.py` and `hazard.py` patch the two seams this issue proposes to change and
then call the **real** `project`, `check_canonicality` and gate resolvers. They are a
measurement harness, not the implementation — RED owns that.

## What the probes found

**1 — the round trip holds, and the contract needs one thing more than planned.**
747 files written, 744 carrying the subtree, `check_canonicality` canonical, digest
stable across hydrate + re-project. Committed shape:

    external_refs:
      github:
        issue: '2029'

Probe 1c is the finding that changed the plan: `'1975'` and `1975` do **not** produce
the same bytes, the store column is `TEXT`, and `FIELD_TYPES` types `external_refs` as
`dict` and reaches no deeper. So an unquoted hand-edit reads back as an `int` and breaks
canonicality with no schema violation to explain it. **The contract must type the leaf,
not just the container.**

**2 — the hazard is total, and the fix is within scope.** Sampling 174 live issues whose
branch *and* feature both resolve today, driven through the real gate resolvers:

| | branch resolves | feature resolves | keys lost |
|---|---|---|---|
| before hydrate | 174/174 | 174/174 | — |
| after today's wholesale replace | **0/174** | **0/174** | 359 `feature`, 195 `branch`, 75 `created`, 75 `id`, 1 `worktree` |
| after the proposed merge + refs restore | 174/174 | 174/174 | none |

Not degraded — zero. And repaired completely by changing `hydrate`'s write semantics,
so `STRIPPED_AT_PROJECTION` does not have to open and the issue does not grow.

**3 — three independent reasons to exclude, not one.**

| excluded | rows | ground |
|---|---|---|
| `(claude, session)` | 154 | **determinism** — `last_seen_at` is refused by `assert_deterministic`, and `build_documents` refuses the whole corpus on the first fault. Wholesale serialization makes the projection *unwritable*, not merely leaky. |
| the row's `data` blob | 819 of 1,104 | **the ruling** — the blob is determinism-clean, so nothing mechanical stops it; it carries `_recovery`, which #1622 ruled DROP. |
| `(github, issue)` on `wmbt` | 56 | **kind** — those objects are not projected, so the ref has no document to ride in. |

What is admitted is well-shaped: 1,104 `(github, issue)` rows, 0 non-digit `ref_value`s,
0 objects carrying more than one. The mapping is strictly 1:1, so the subtree needs no
list and no ordering rule. 304 of the work-item rows belong to `COMPLETE` objects the
projection archives out — which is why `hydrate` restores and never deletes.

## A note on the integers

The corpus grows as issues are authored, so absolute counts move between runs;
authoring #2024 and #2025 moved the document count while this lab was being written.
What does not move is the shape of the answer: the identity count is **zero**, for
every document, at every reading. Re-run the probes rather than trusting the numbers
quoted here.
