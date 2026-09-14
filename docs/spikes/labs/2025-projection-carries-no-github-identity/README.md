# Lab — #2025: the committed projection carries no GitHub identity

Three hypotheses, each stated so it could be false, each with its own probe.

| probe | hypothesis | verdict |
|---|---|---|
| `roundtrip.py` | a projection carrying `external_refs` still satisfies `project(hydrate(p)) == p` byte-for-byte and passes `check_canonicality` | **HELD** — and surfaced the str/int contract gap |
| `hazard.py` | today's wholesale-replace `hydrate` destroys `feature` and `branch`, and the destruction reaches the gates that read them | **HELD** — 174/174 → 0/0 on both gates; the proposed merge restores 174/174 |
| `subtree.py` | the refs table cannot be serialized wholesale, and every excluded row has a stateable reason | **HELD** — three independent exclusion grounds |
| `adversarial.py` | the proposed fix is itself correct | **REFUTED** — four defects, three of them in the fix |
| `scope.py` | tightening the contract to `github.issue` is safe | **REFUTED** — it would refuse legal bot writes |

## Running them

    ./lab.sh                 # the corpus census + the hazard, end to end
    PYTHONPATH=../../../../src python3 roundtrip.py <control-root>
    PYTHONPATH=../../../../src:. python3 hazard.py  <control-root>
    PYTHONPATH=../../../../src python3 subtree.py     <control-root>
    PYTHONPATH=../../../../src:. python3 adversarial.py <control-root>
    PYTHONPATH=../../../../src python3 scope.py       # no store needed

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

**4 — the proposed fix had four defects, and `check_canonicality` saw none of them.**

| case | proposed behaviour | verdict |
|---|---|---|
| 4a a malformed nested ref | `'1975'`, `1975`, `{"number":1975}`, `["1975"]` | all four **ADMITTED** — `validate_document` types `external_refs` as `dict` and reaches no deeper |
| 4b a ref colliding with an existing binding | `link()` is `ON CONFLICT DO UPDATE SET object_uid` | **silently re-pointed**; the proposed hydrate checked uniqueness only *within* the document set |
| 4c an existing ref row's `data` blob | `link(..., data=None)` → `_dumps(None)` = `'{}'` | **wiped**; 1,103 rows carry a non-empty blob |
| 4d a bot-written `jira` subtree | `build_document` popped and rebuilt from the table | **destroyed** |

4b, 4c and 4d are faults *in the proposed fix* — each one the same
replace-where-merge-was-required defect the issue exists to correct. And
`check_canonicality` reports `projection is canonical (747 object(s))` through all four,
because it hydrates into an **empty** `MemoryStore` (`projection.py:719-722`): no existing
object to preserve, no existing ref to collide with, no blob to wipe, no foreign provider
to destroy. Acceptances that lean on it for the crux pass vacuously.

**5 — the contract must stay open.**

    apply_updates:  github/issue -> ADMITTED   github/pr    -> ADMITTED
                    jira/ticket  -> ADMITTED   linear/issue -> ADMITTED

    _bot_only:      ours={github, jira}  theirs={github, linear}  base={github}
                    merged -> {github, jira, linear}    conflict -> None

`validate_update` constrains the uid, the bot namespace, authoritativeness and provider
*identity* — never the provider or ref-kind vocabulary. `_bot_only` unions disjoint
providers by design. Narrowing `external_refs` to `github.issue` would refuse three of four
legal writes and make that merge result unwritable. The contract therefore stays open and
types only the `github.issue` leaf.

`apply_updates` also already writes `refs[provider][ref_kind] = value` — the nested shape
the issue described as a proposal is the shape the sanctioned writer has always emitted.

## A note on the integers

**Where they come from:** the live Control Root store at
`<control-root>/.atdd/state/state.sqlite` — *not* `main/.atdd/state/state.sqlite`, which
is a 0-byte placeholder. A second party resolving the Control Root from inside the repo
will find the empty one and reproduce nothing; that is what happened in review. `lab.sh`
walks up to the real root, honours `ATDD_CONTROL_ROOT`, and prints which root it used.

The corpus grows as issues are authored, so absolute counts move between runs;
authoring #2024 and #2025 moved the document count while this lab was being written.
What does not move is the shape of the answer: the identity count is **zero**, for
every document, at every reading. Re-run the probes rather than trusting the numbers
quoted here.
