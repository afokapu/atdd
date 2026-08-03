# Decommission fill-later — quarantined legacy validators (#1365)

Legacy persona-validators whose convention variant does **not** provide independent real
coverage, so the **legacy test remains the only real coverage** and is **kept**. Recorded here
with an explicit reason so a later pass can revisit them (e.g. once the variant gains a real
fault-injection differential).

Two files remain deferred. The other 12 quarantined legacy validators — the 9 helper-coupled
files (Groups A and B) and the 3 binding-family `bind_rule` emitters (Group C) — were **retired
in #1385**: their shared helpers and `bind_rule` emitters were relocated to support/binder
modules, the importers and rule bindings were repointed, and the legacy files were deleted. The
parity scaffolding that guarded them (the pre-flight classifier, `legacy-validator-map.yaml`,
Y001/Y002, the `_support` oracle helpers, and the migration reports) was torn down in the same
change.

| Legacy validator (KEPT) | Convention variant | Reason kept | Revisit-when |
|---|---|---|---|
| `src/atdd/planner/validators/test_theme_archetype_alignment.py` | `coherence/theme_archetype_alignment` | **function-level parity** — a same-file fault-injection differential is structurally impossible; parity was proven only at the scan-function level, so the variant is not independent real coverage. The rule `planner.theme.archetype-alignment` still binds to the legacy validator. | the variant gains a real on-disk fault-injection differential that catches an archetype/theme misalignment on the composed graph |
| `src/atdd/coach/validators/test_validate_contract_consumers.py` | `resolution/contract_consumer_resolution` | **not-measurable / legacy-hermetic** (`test_legacy_parity_not_measurable_via_injection`) — no real consume→contract reference data to inject against in this repo; the legacy test is hermetic (builds its own tmp fixture) and is the only coverage. | the repo grows real consume→contract references so a live-graph injection differential becomes measurable |

## Notes
- The oracle (`legacy_caught`/`assert_fault_parity`) legs in these two variants **were** dropped in
  the #1365 kill-oracle sweep (dual-maintenance removal); the legacy files themselves stay.
- Neither legacy file's rule was repointed — they remain bound to their legacy validators until revisited.
- Do NOT delete these two files in a "cleanup" pass without re-establishing real convention coverage first.
- The permanent **Y003 guards are kept** (they are not scaffolding).
