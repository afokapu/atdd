# Lab — #2025: the committed projection carries no GitHub identity

Three hypotheses, each stated so it could be false:

1. The projection carries no GitHub identity today, and after the #1622-ruled
   migration there is no identity anywhere in the projected document.
2. Folding the `external_refs` table into the document *wholesale* is not merely
   untidy but impossible: some rows would make the projection unwritable.
3. Making `hydrate` a field-scoped merge resolves the deletion hazard without
   breaking `project(hydrate(p)) == p`.

## Running it

    ./lab.sh

Reads `<control-root>/.atdd/state/state.sqlite` **through a copy** and writes
nothing back. `store_migration.migrate_store()` is run on the copy first, so the
measurements describe the world the projection cutover is about to create, not
the pre-migration one.

## Measured 2026-09-14

`./lab.sh` prints all of the below. The corpus GROWS as issues are authored, so
the absolute counts move between runs — authoring #2024 and #2025 themselves moved
the document count from 743 to 746 while this lab was being written. What does not
move is the shape of the answer: the identity count is **zero**, and it is zero for
every document. Treat the ratios, not the integers, as the finding.

Reading of 2026-09-14, against 1,050 work items / 1,257 external refs:

| claim | result |
|---|---|
| 1 | 746 projectable documents; **0** carry any `external_refs` key. The table holds 1,103 `(github, issue)` rows, 743 of them on projected uids. Every `ref_value` is all-digits; the mapping is strictly one-to-one. |
| 2 | The other 154 rows are `(claude, session)` with `data = {"last_seen_at": "<ISO-8601>"}`. `assert_deterministic` catches that twice — `_key_fault` on the `_at` suffix and `_TIMESTAMP_VALUE_RE` on the value — and `build_documents` refuses the whole corpus on the first fault. The lab prints the actual refusal: `nondeterministic projection content claude:6453e644-… at field 'external_refs.claude.last_seen_at': is a wall-clock timestamp field`. Separately, 819 of the 1,103 GitHub rows carry a `data._recovery` bag, the key #1622 ruled DROP. |
| 3 | Merge-hydrate preserves every stripped key (`feature` 566→566, `branch` 457→457, `created`/`id` 79→79, `worktree` 1→1) and the round trip stays byte-identical. Today's wholesale-replace hydrate on the same inputs deletes 358 `feature`, 195 `branch`, 75 `created`, 75 `id`, 1 `worktree`. |

Hydrated into a **fresh, empty** store — the actual inbound case — the prototype
yields 743 external-refs rows (today: 0) and resolves a real issue number to its
uid. That object's `branch` and `feature` come back `None`, which is correct:
those stay stripped, and a peer was never going to inherit a useful value for
either.

Two further findings that changed the plan:

- **`hydrate` must restore, never delete.** The table holds far more work-item
  rows than there are projected uids — the surplus belongs to `COMPLETE` objects
  that `ARCHIVED_PHASES` keeps out of the projection. A hydrate that made the
  table *match* the projection would delete those live bindings on first ingest.
- **Duplicate issue claims need an explicit refusal.** `ExternalRefStore.link` is
  `ON CONFLICT(provider, ref_kind, ref_value) DO UPDATE SET object_uid=excluded.object_uid`
  — last writer silently wins. Two peers binding different uids to one issue
  number is exactly the object conflict this train exists to resolve.
