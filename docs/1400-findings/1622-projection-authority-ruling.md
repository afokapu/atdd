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
