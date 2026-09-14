# #1622 — ruling: the committed projection is a CI round-trip artifact, not a recovery source

**Ruled by:** the operator, 2026-09-13. **Settles:** `issue_number` and `_recovery`.

The key-disposition findings escalated one question they could not answer read-only
(`1622-key-disposition-a.md` §"confidence"):

> A ruling that the committed projection is *only* the CI round-trip check and never a
> store-recovery source → DROP becomes correct. `hydrate`'s docstring ("the read half of
> the CI guarantee") argues that way; the schema's "Authoritative for shared project
> state" argues the other. **Not settleable read-only — owner of the projection spec must
> call it.**

## The ruling

The committed projection is **authoritative for shared state** — what peers agree the
objects are — and is **not** a source the store is rebuilt from. `hydrate` exists to
prove determinism: CI hydrates what the branch committed and re-projects it. It is not
disaster recovery. The SQLite store is what you restore from.

## Why this was the honest reading

- `hydrate()` upserts `store.objects` **only** — it never repopulates `external_refs`.
  So the projection already fails as a recovery source today: a store rebuilt from it
  cannot answer "which work item is issue #1622?" regardless of what rides in the bag.
- Choosing EXTERNAL_REFS would therefore *not* have been the relocation the findings
  scoped. It would project a value `hydrate` ignores, and would additionally require
  teaching `hydrate` to restore the refs table — work in nobody's plan.
- `check_canonicality` is unaffected: `project(hydrate(committed)) == committed` holds
  under stripping, with no fixpoint problem.

## Consequences

| Key | Carriers | Was | Now |
|---|---|---|---|
| `issue_number` | 515 projectable | EXTERNAL_REFS (escalated) | **DROP** — `external_refs`→uid is authoritative and lives in the store |
| `_recovery` | 512 projectable / 767 total | STRIP-not-drop (hydrate blocker) | **DROP** — the blocker was this question |

Together these are 1,027 of the 3,708 unprojectable-field defects.

## Discharged prerequisite — the `_recovery` archive

The findings required this before any drop, because `ObjectStore.upsert` is a wholesale
replace, so the first hydrate after the projector stops emitting `_recovery` deletes the
forensic trail of the 2026-07-20 data-loss incident permanently:

> fix hydrate's replace semantics or archive the 515 bags out-of-band first.

Archived: **`docs/1400-findings/1622-recovery-bags-archive.json`** — all 767 bags
(the count has grown from the 515 measured on 2026-08-01), captured from a read-only
copy of the Control Root store.

**Still open, and NOT settled by this ruling:** 7 of those bags carry
`needs_operator_review: true`, on live work items —

    REFACTOR  introduce-convention-validator-family-template-architecture
    REFACTOR  map-legacy-validators-to-convention-parity-matrix
    REFACTOR  plan-guidelines-consumer
    SMOKE     planner-naming-validators
    RED       runtime-spec-interlockingrunner-is-called-by-station-master-
    PLANNED   t2
    PLANNED   x

The disposition record assumed DROP is safe once "the operator declares the record
spent." Seven records say they are not spent. They are preserved in the archive, so the
drop is no longer destructive — but the reviews remain owed, and nothing in #1622
discharges them.

## Scope note for Phase 2

The projection schema digest (`extensions_lock.projection_schema_digest`) is derived from
`FIELD_TYPES` / `REQUIRED_FIELDS` / `PHASES` / `STATES`, not from the authored
`.schema.json`. Qualifying the schema's prose (below) does not move the lock. The GROW and
DROP work does.

---

## Superseded in part by #2025, 2026-09-14

**What is superseded:** the premise, not the rule.

This ruling rested on a premise it stated openly — that the committed projection "is not
a source the store is rebuilt from" — and it was the honest reading at the time, because
`hydrate` really did rebuild `store.objects` and nothing else. The operator is now
adopting git as the transport to GitHub: store -> canonical YAML -> commit -> a workflow
reconciles GitHub to match, and inbound, a peer's committed projection is hydrated. That
makes the projection a real transport in both directions, and the premise no longer
holds.

The ruling named this work itself, as the reason EXTERNAL_REFS was not chosen:

> It would project a value `hydrate` ignores, and would additionally require teaching
> `hydrate` to restore the refs table — work in nobody's plan.

It is now in the plan. #2025 does exactly that.

**What survives, untouched.** The narrow rule this document exists to record:

- Core does not author provider identity into `obj.data`. The bot writes `external_refs`
  — `.atdd/policy/field-ownership.yaml` keeps `writer: extension_bot`, `rule: bot-only`,
  `lifecycle_readable: false`, and I7 (spec §8.2 rule 5) still forbids core consulting it
  for a lifecycle decision. The field is *carried*, never *consulted*.
- `issue_number` stays DROPPED from the data bag. Its authority is the `external_refs`
  table, exactly as ruled. What changes is that the projection now carries a defined
  slice of that table, rather than carrying nothing.
- `_recovery` stays DROPPED, and stays out of the projection. #2025 carries the refs
  table's `ref_value` only and **not** the row's `data` blob — 819 of the 1,100 GitHub
  rows carry a `_recovery` bag, and readmitting it through `external_refs` would reverse
  this ruling by the back door.
- The seven `needs_operator_review: true` records above remain owed. Nothing here
  discharges them either.

**What changes.** Two things, both consequences of the premise going away:

1. `external_refs` is projected — as an explicitly enumerated subtree
   (`{github: {issue: "<digits>"}}`), never a wholesale serialization of the table. The
   other 151 rows are `(claude, session)` carrying `last_seen_at`; a wall-clock reading
   under an `_at` key is refused by `assert_deterministic`, so serializing the table
   whole would not merely leak session metadata into shared state, it would make the
   projection unwritable.

2. **The `STRIPPED_AT_PROJECTION` hazard this document flagged is resolved by fixing
   `hydrate`, not by un-stripping.** This ruling recorded the hazard precisely —

   > `ObjectStore.upsert` is a wholesale replace, so the first hydrate after the
   > projector stops emitting `_recovery` deletes the forensic trail […] permanently

   — and discharged it for `_recovery` by archiving out-of-band. Once hydrate is a real
   inbound path that answer does not scale: measured on a migrated copy of the live
   store, one `project`+`hydrate` cycle deletes 355 `feature` values (read by the
   smoke-obligation gate) and 192 `branch` values (read by the pre-commit registration
   gate). The resolution is that a wholesale replace was never the right semantics for an
   inbound merge — a document that omits `branch` is not claiming the object has no
   branch, it is declining to have an opinion. `hydrate` becomes a field-scoped merge
   that carries the stripped keys forward from the object already in the store.

   So `branch` and `feature` stay stripped, for the reasons given above: `branch` is
   per-machine, and 49% of `feature`'s non-null values are the #2006 generator
   placeholder. Publishing 172 false bindings as authoritative shared state was the harm
   this ruling avoided, and it is still avoided.

`check_canonicality` is unaffected: the carried-forward keys are stripped again on the
way out, so `project(hydrate(committed)) == committed` still holds byte-for-byte.
