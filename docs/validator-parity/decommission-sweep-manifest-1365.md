# #1365 — Full-sweep decommission manifest (Tier-1 + Tier-2 executing legacy validators)

**Status:** PLANNED — awaiting operator sign-off on this partition before any edit/delete.
**Scope:** the operator-directed *sweep* strategy (supersedes the conservative binding-only
batch). Kill the parity oracle everywhere, then sweep-retire every **executing** legacy
validator whose convention variant is `both` (Tier-1) **or** `convention-only` (Tier-2, strictly
stricter than legacy), in one pass. Quarantine the non-executing residue. **Then, as the final
phase (§f), tear down the now-spent parity scaffolding** (classifier, map, migration docs, oracle
helpers, Y001/Y002) — deleted *last*, since the sweep uses them while running.

Regenerated live from `scripts/decommission_manifest.py` + `docs/validator-parity/family-parity-report.md`.
Every **DELETE** variant's real execution was confirmed by running its tests
(`pytest src/atdd/validators/conventions/<family>/<variant>.py` → passed, no skips). Live
dangling-ref scan at authoring time: **0**.

## Partition summary

| bucket | count | action |
|---|---|---|
| **(a) DELETE** | 19 | repoint rule(s) → drop oracle → delete legacy file |
| **(b) MAP-BLOCKED** | 2 | fix `legacy-validator-map.yaml` target + re-anchor acceptance, then delete |
| **(c) QUARANTINE** | 2 | KEEP legacy (only real coverage); park with reason |
| **(d) ALREADY-GONE** | 9 | legacy absent, 0 dangling refs — verify-only, no action |
| **(e) KILL-ORACLE** | 14 variants | first commit: drop the `subprocess pytest <legacy nodeid>` cross-check |
| **(f) SCAFFOLDING TEARDOWN** | final phase | delete spent classifier + map + migration docs + oracle helpers + Y001/Y002 (re-anchor first) |

**Two guards are the acceptance spine** (`wmbt:validate-conventions:Y003`):
`Y003-SMOKE-001-no-dangling-legacy-reference` + `Y003-SMOKE-002-coverage-preserved`.

> **Safety check (the one gate before deleting each file):** the legacy file is deleted **only
> if** its convention variant TRULY EXECUTES and asserts something real (not vacuous / xfail /
> stub). Confirmed for all 19 DELETE + 2 MAP-BLOCKED. The 2 QUARANTINE files fail this check.

> **Bidirectional-binding CI catch still applies.** `tester.acceptance-violation.validator-binding-must-be-bidirectional`
> fails if a plan acceptance's anchoring test is deleted with no surviving anchor. Acceptance-anchored
> DELETE/MAP-BLOCKED files below carry a **re-anchor** note; GREEN must retire or re-anchor each
> (or confirm a surviving dual-anchor) before deletion.

New-target function names below are the variant's **executing fault-injection test**; the
kill-oracle commit drops the legacy leg and may rename `*_legacy_parity` → `*_convention_fault`.
Exact final nodeids are shown in the GREEN diff before deletion.

---

## (a) DELETE — 19 files

| # | Legacy file (delete) | Repoint rule(s): OLD `validator` → NEW variant nodeid | Oracle to drop | Acceptance re-anchor |
|---|---|---|---|---|
| 1 | `src/atdd/coach/validators/test_commit_trailers_binding.py` | `coach.commit-trailers.{phase,wmbt-urn,agent-id,issue}-required` (×4): OLD `test_commit_trailers_binding::test_commit_trailers_rule_family_emits_each_required_trailer_id` → NEW `test_commit_trailers_rule_binding::test_commit_trailers_rule_binding_convention_fault` | `binding/test_commit_trailers_rule_binding.py` | — |
| 2 | `src/atdd/coach/validators/test_e001_unit_001_spawn_cli_launches_session.py` | `coach.spawn.atdd-spawn-cli`: OLD `test_e001_unit_001_spawn_cli_launches_session::test_spawn_emits_agent_spawned_event_conforming_to_schema` → NEW `test_spawn_cli_rule_binding::test_spawn_cli_rule_binding_convention_fault` | `binding/test_spawn_cli_rule_binding.py` | `acc:spawn-agents:E001-UNIT-001-spawn-cli-launches-session` — **dual-anchored** by `coach/commands/tests/test_e001_unit_001_spawn_cli_launches_session.py`; no re-anchor needed (verify catch green) |
| 3 | `src/atdd/coach/validators/test_fix_hint_completeness.py` | `coach.rule-id.fix-hint-completeness`: OLD `test_fix_hint_completeness::test_every_fix_hint_satisfies_completeness_contract` → NEW `test_rule_has_fix_hint::test_rule_has_fix_hint_is_convention_only_not_legacy_parity` (convention-only) | `presence/test_rule_has_fix_hint.py` | — |
| 4 | `src/atdd/coach/validators/test_no_hardcoded_rule_severity.py` | `coach.rule-id.no-hardcoded-rule-severity`: OLD `test_no_hardcoded_rule_severity::test_no_hardcoded_rule_severity_in_migrated_validators` → NEW **path-qualified** `src/atdd/validators/conventions/binding/test_no_hardcoded_rule_severity::test_no_hardcoded_rule_severity_convention_fault` (⚠ stem collision) | `binding/test_no_hardcoded_rule_severity.py` | — |
| 5 | `src/atdd/coach/validators/test_urn_traceability.py` | PLATFORM — no rule binding (`resolution/urn_traceability` convention-only) | none | — |
| 6 | `src/atdd/planner/validators/test_dispatch_registry.py` | `planner.train.{dispatch-map-is-registry,dispatch-composite-key-exceptional}` (×2): OLD `test_dispatch_registry::test_real_dispatch_entries_well_formed` → NEW `test_dispatch_map_is_registry::test_fault_caught_by_convention_and_legacy` | `schema/test_dispatch_map_is_registry.py` | — |
| 7 | `src/atdd/planner/validators/test_feedback_loop_smoke_closes_the_loop.py` | `planner.smoke.feedback-loop-close-the-loop` (decl `tester/conventions/smoke.convention.yaml`): OLD `test_feedback_loop_smoke_closes_the_loop::test_every_feedback_loop_feature_has_close_the_loop_smoke` → NEW `test_feedback_loop_close_the_loop::test_feedback_loop_catches_injected_fault` | `presence/test_feedback_loop_close_the_loop.py` | — |
| 8 | `src/atdd/planner/validators/test_hierarchy_coverage.py` | `coder.coverage.every-feature-must-have`, `coder.coverage.every-implementation-must-have`, `coder.design.hierarchy-coverage`, `planner.coverage.every-wmbt-must-have`, `tester.coverage.tracking-manifest-must-be` (×5): OLD `test_hierarchy_coverage::{test_all_features_have_implementations, test_all_implementations_have_tests, test_all_wmbts_have_acceptances, test_telemetry_manifest_complete}` → NEW `coverage/test_hierarchy_coverage::test_fault_injection_convention_catches_legacy_warn_only` | none | — |
| 9 | `src/atdd/planner/validators/test_no_cross_wagon_consume_cycle.py` | `planner.wagon.no-consume-cycle`: OLD `test_no_cross_wagon_consume_cycle::test_no_cross_wagon_consume_cycle` → NEW `acyclicity/test_no_cross_wagon_consume_cycle::test_fault_injection_legacy_parity` (→ `_convention`) | `acyclicity/test_no_cross_wagon_consume_cycle.py` | — |
| 10 | `src/atdd/planner/validators/test_no_orphan_nodes.py` | `planner.relationship.no-orphan-nodes`: OLD `test_no_orphan_nodes::test_no_orphan_convention_nodes` → NEW `coverage/test_no_orphan_nodes::test_fault_injection_legacy_parity_both_catch` | none | `acc:author-atdd-substrate:C008-SMOKE-001-no-orphan-nodes` — retire/re-anchor |
| 11 | `src/atdd/planner/validators/test_smoke_synthetic_fixture_bypass.py` | `planner.smoke.synthetic-fixture-bypass` (decl `tester/conventions/smoke.convention.yaml`): OLD `test_smoke_synthetic_fixture_bypass::test_no_smoke_tests_use_synthetic_fixtures` → NEW `policy/test_smoke_synthetic_fixture_bypass::test_fault_injection_legacy_parity` | `policy/test_smoke_synthetic_fixture_bypass.py` | **6 accs**: `acc:govern-lifecycle:E028-UNIT-004`, `E028-UNIT-005`, `E028-INTEGRATION-001`, `E028-SMOKE-001`, `L002-UNIT-001`, `L002-SMOKE-001` — retire/re-anchor |
| 12 | `src/atdd/planner/validators/test_theme_commons_coach_boundary.py` | `planner.theme.commons-coach-boundary`: OLD `test_theme_commons_coach_boundary::test_commons_wagons_do_not_import_coach` → NEW `boundary/test_theme_commons_coach_boundary::test_fault_injection_convention_and_legacy_both_catch` | none | `acc:govern-lifecycle:C003-UNIT-001`, `C003-SMOKE-001` — retire/re-anchor |
| 13 | `src/atdd/planner/validators/test_theme_urn_namespace_matches.py` | `planner.theme.urn-namespace-matches`: OLD `test_theme_urn_namespace_matches::test_produced_urn_prefix_matches_theme` → NEW `coherence/test_theme_urn_namespace_matches::test_fault_both_catch_function_level` | none | `acc:govern-lifecycle:C004-UNIT-001`, `C004-SMOKE-001` — retire/re-anchor |
| 14 | `src/atdd/planner/validators/test_theme_zero_mandatory.py` | `planner.theme.theme-zero-mandatory`: OLD `test_theme_zero_mandatory::test_commons_is_always_in_resolved_theme_set` → NEW `presence/test_theme_zero_mandatory::test_theme_zero_catches_injected_fault` | `presence/test_theme_zero_mandatory.py` | `acc:govern-lifecycle:C006-UNIT-001`, `C006-UNIT-002`, `C006-SMOKE-001` — retire/re-anchor |
| 15 | `src/atdd/planner/validators/test_train_validation.py` | `planner.train.registry`: OLD `test_train_validation::test_train_files_exist_for_registry_entries` → NEW `resolution/test_train_validation::test_fault_injection_and_legacy_parity` (→ `_convention`) | `resolution/test_train_validation.py` | — |
| 16 | `src/atdd/planner/validators/test_wagon_coupling_complexity.py` | `planner.wagon.coupling-complexity`: OLD `test_wagon_coupling_complexity::test_wagon_coupling_complexity_reported` → NEW `sizing/test_wagon_coupling_complexity::test_fault_injection_legacy_parity` | none | — |
| 17 | `src/atdd/planner/validators/test_wagon_separability.py` | `planner.wagon.separability`: OLD `test_wagon_separability::test_wagon_separability_reported` → NEW `sizing/test_wagon_separability::test_fault_injection_legacy_parity` | none | — |
| 18 | `src/atdd/planner/validators/test_wmbt_has_smoke_acceptance.py` | `planner.wmbt.must-have-smoke-acceptance`: OLD `test_wmbt_has_smoke_acceptance::test_every_wmbt_has_smoke_acceptance` → NEW `coverage/test_wmbt_has_smoke_acceptance::test_fault_injection_legacy_parity_both_catch` | none | `acc:govern-lifecycle:E003-INTEGRATION-001`, `E003-SMOKE-001` — retire/re-anchor |
| 19 | `src/atdd/tester/validators/test_hierarchy_coverage.py` | same 5 rules as #8 (shared `coverage/hierarchy_coverage` variant) | none | — |

---

## (b) MAP-BLOCKED — 2 files (fix `docs/validator-parity/legacy-validator-map.yaml` + re-anchor acceptance, then delete)

Both are acceptance-anchored **and** carry a stale `proposed_target_path` that does not resolve —
deleting as-is would trip `test_no_unsafe_legacy_deletion` (Y001) **and** the bidirectional-binding catch.

| Legacy file (delete) | Variant(s) | Oracle to drop | Map fix (before delete) | Acceptance re-anchor |
|---|---|---|---|---|
| `src/atdd/coach/validators/test_e026_bypass_inventory_guard.py` | `policy/bypass_inventory` | `policy/test_bypass_inventory.py` | `proposed_target_path: …/policy/test_bypass_inventory_baseline.py` → **`…/policy/test_bypass_inventory.py`** (shipped variant); ensure `parity_status ∈ {direct,split,merged,superseded}` | `acc:govern-lifecycle:E026-UNIT-005-meta-guard-fails-when-bypass-count-grows`, `acc:govern-lifecycle:E030-UNIT-003-meta-guard-baseline-is-zero` — retire/re-anchor |
| `src/atdd/coach/validators/test_e032_smoke_001_live_freedom_layer_passes_flipped_validator.py` | `grammar/freedom_layer_bash_scope_grammar` **+** `policy/freedom_layer_bash_scope` | `grammar/test_freedom_layer_bash_scope_grammar.py`, `policy/test_freedom_layer_bash_scope.py` | `parity_status: merged`, `proposed_target_path: …/policy/test_freedom_layer_no_forbidden_command.py` (does not resolve) → point at the shipped variant(s) above | `acc:spawn-agents:E032-SMOKE-001-live-freedom-layer-passes-flipped-validator` — retire/re-anchor |

---

## (c) QUARANTINE — 2 files (KEEP legacy; it is the only real coverage) → `docs/validator-parity/decommission-fill-later.md`

| Legacy file (KEEP) | Variant | Reason (fails the execute-real-coverage safety check) |
|---|---|---|
| `src/atdd/planner/validators/test_theme_archetype_alignment.py` | `coherence/theme_archetype_alignment` | **function-level parity** — a same-file fault-injection differential is structurally impossible; parity was proven only at the scan-function level, so the variant is not independent real coverage. Legacy remains the enforcing test. |
| `src/atdd/coach/validators/test_validate_contract_consumers.py` | `resolution/contract_consumer_resolution` | **not-measurable / legacy-hermetic** (`test_legacy_parity_not_measurable_via_injection`) — no real consume→contract reference data to inject against in this repo; legacy test is hermetic and is the only coverage. |

> Note: their variants' oracle legs are still dropped in the kill-oracle sweep (dual-maintenance
> removal); the legacy files stay. Each gets an explicit per-item entry in `decommission-fill-later.md`.

---

## (d) ALREADY-GONE — 9 files (legacy absent; 0 dangling refs; verify-only, no action)

| Legacy file (already deleted) | Covering variant |
|---|---|
| `src/atdd/coach/validators/test_composition_data_shipped.py` | `composition/package_data_ships_convention_nodes` |
| `src/atdd/coach/validators/test_e009_unit_001_convention_declares_runtime_artifacts_rule.py` | `binding/runtime_artifacts_rule_binding` |
| `src/atdd/coach/validators/test_no_stale_suppressions.py` | `policy/no_stale_suppressions` |
| `src/atdd/coach/validators/test_phase_machine_init_pre_commit_gate.py` | `presence/phase_machine_init_precommit_gate` |
| `src/atdd/coach/validators/test_rule_disposition_required.py` | `presence/rule_has_disposition` |
| `src/atdd/planner/validators/test_draft_wagon_registry.py` | `resolution/draft_wagon_registry` |
| `src/atdd/planner/validators/test_plan_urn_resolution.py` | `resolution/plan_urn_resolution` |
| `src/atdd/planner/validators/test_train_family_matches_terminal_contract.py` | `coherence/train_family_matches_terminal_contract` |
| `src/atdd/planner/validators/test_wmbt_consistency.py` | `coherence/wmbt_consistency` |

---

## (e) KILL-ORACLE — 14 variant files (the un-gating first commit)

Drop the `subprocess pytest <legacy nodeid>` cross-check (`assert_fault_parity(…LEGACY_NODEID…)` /
`legacy_caught` / `legacy_catches` legs) from every executing convention variant. Each variant's own
clean-baseline + real fault-injection remain the live coverage. This is committed **first** — it
removes the dual-maintenance that forced the 3-files-at-a-time crawl.

| # | Variant file | Legacy source it cross-checks | Downstream bucket |
|---|---|---|---|
| 1 | `src/atdd/validators/conventions/binding/test_commit_trailers_rule_binding.py` | test_commit_trailers_binding | DELETE |
| 2 | `src/atdd/validators/conventions/binding/test_no_hardcoded_rule_severity.py` | test_no_hardcoded_rule_severity | DELETE |
| 3 | `src/atdd/validators/conventions/binding/test_spawn_cli_rule_binding.py` | test_e001_unit_001_spawn_cli_launches_session | DELETE |
| 4 | `src/atdd/validators/conventions/acyclicity/test_no_cross_wagon_consume_cycle.py` | test_no_cross_wagon_consume_cycle | DELETE |
| 5 | `src/atdd/validators/conventions/schema/test_dispatch_map_is_registry.py` | test_dispatch_registry | DELETE |
| 6 | `src/atdd/validators/conventions/presence/test_feedback_loop_close_the_loop.py` | test_feedback_loop_smoke_closes_the_loop | DELETE |
| 7 | `src/atdd/validators/conventions/presence/test_rule_has_fix_hint.py` | test_fix_hint_completeness | DELETE |
| 8 | `src/atdd/validators/conventions/presence/test_theme_zero_mandatory.py` | test_theme_zero_mandatory | DELETE |
| 9 | `src/atdd/validators/conventions/policy/test_smoke_synthetic_fixture_bypass.py` | test_smoke_synthetic_fixture_bypass | DELETE |
| 10 | `src/atdd/validators/conventions/resolution/test_train_validation.py` | test_train_validation | DELETE |
| 11 | `src/atdd/validators/conventions/policy/test_bypass_inventory.py` | test_e026_bypass_inventory_guard | MAP-BLOCKED |
| 12 | `src/atdd/validators/conventions/policy/test_freedom_layer_bash_scope.py` | test_e032_smoke_001_live_freedom_layer… | MAP-BLOCKED |
| 13 | `src/atdd/validators/conventions/grammar/test_freedom_layer_bash_scope_grammar.py` | test_e032_smoke_001_live_freedom_layer… | MAP-BLOCKED |
| 14 | `src/atdd/validators/conventions/coherence/test_theme_archetype_alignment.py` | test_theme_archetype_alignment | QUARANTINE (legacy kept) |

---

## The two guards (acceptance spine, `wmbt:validate-conventions:Y003`)

1. **no-dangling-legacy-reference** — no rule `implementation.ref`/`validator` resolves to a deleted
   `src/atdd/*/validators/test_*.py`. Complements Y001 (map safety) at the rule-ref level.
2. **coverage-preserved** — each repointed rule binds to a convention variant that executes (real
   traversal, not xfail/stub). Complements Y002 (preflight visibility).

---

## (f) SCAFFOLDING TEARDOWN — final phase (operator scope addition)

Delete the now-spent migration scaffolding **last** — the sweep itself still uses these tools while
running, so they come out only **after** the legacy sweep + guards + CI-green. Each `_support` oracle
helper is deleted **only once no variant references it** (post kill-oracle). Y001/Y002 get the **same
bidirectional-binding discipline** as the legacy sweep (retire/re-anchor their plan acceptances first,
or CI trips).

### DELETE (scaffolding)
| target | note |
|---|---|
| `scripts/decommission_manifest.py` | pre-flight classifier — spent |
| `docs/validator-parity/legacy-validator-map.yaml` | parity map — spent |
| `docs/validator-parity/convention-validator-parity-audit.md` | migration report |
| `docs/validator-parity/family-parity-report.md` | migration report (verdict authority — spent post-sweep) |
| `docs/validator-parity/catch-matrix.md` | migration report |
| `docs/validator-parity/shadow-run-report.md` | migration report |
| `docs/validator-parity/decommission-manifest.md` | stale generated snapshot |
| `docs/validator-parity/p0-legacy-vs-convention-gap-report.md` | migration report |
| `docs/validator-parity/registry-nodes-migration-audit.md` | migration report |
| `docs/validator-parity/single-node-implref-ingestion-findings.md` | migration report |
| `docs/validator-parity/legacy-validator-decommission-report.md` | migration report |
| `docs/validator-parity/stricter-findings-adjudication.md` | migration report |
| `docs/validator-parity/decommission-assertions.md` | migration report |
| oracle helper `assert_fault_parity` (+ its `_legacy_caught`) in `binding/_parity_support.py` | keep `assert_clean_baseline` + `assert_fault_convention_only` (still used) |
| oracle helper `legacy_caught` in `coherence/_parity.py` | delete once unreferenced post kill-oracle |
| oracle helper `legacy_catches` in `policy/_parity.py` | delete once unreferenced |
| oracle helper `legacy_catches` in `presence/conftest.py` | delete once unreferenced |
| oracle helper `legacy_caught` in `resolution/_parity.py` | delete once unreferenced |
| `src/atdd/validators/conventions/tests/test_y001_no_unsafe_deletion.py` (Y001) | migration-only; **re-anchor first** `acc:validate-conventions:Y001-SMOKE-001-seed` |
| `src/atdd/validators/conventions/tests/test_y002_decommission_preflight_classifier.py` (Y002) | migration-only; **re-anchor first** `acc:validate-conventions:Y002-SMOKE-001-seed` |
| Y001/Y002 plan artifacts | `plan/validate_conventions/Y001.yaml`, `Y002.yaml`; drop from wagon `wmbt:` map + `legacy_decommission` feature `wmbts:`; drop smoke-audit rows |
| parity harness tests `tests/test_catch_matrix.py`, `tests/test_sentinels.py` | scaffolding harness — delete iff they only exercise the parity machinery (verify at GREEN) |

### KEEP (do NOT delete)
| target | why |
|---|---|
| `plan/validate_conventions/Y003.yaml` + the two guard tests | **permanent hygiene** (no-dangling-ref + variant-executes) |
| `docs/validator-parity/decommission-fill-later.md` | residue record (the 2 quarantines) |
| `docs/validator-parity/decommission-sweep-manifest-1365.md` (this file) | PR record |
| the 2 QUARANTINED legacy validators (§c) | only real coverage for their rules |

### REVIEW-AT-GREEN (ambiguous — I will flag, not auto-delete)
`docs/validator-parity/decommission-runbook.md`, `decommission-issue-1207-body.md` (#1207 stays open),
`author-engine-reconciliation-plan.md`, `decomposition-plan.md` — planning/runbook docs that may still
have reference value. I will list these in the GREEN diff for your keep/delete call rather than removing
them unilaterally.

---

## Sequencing

1. Kill-oracle sweep (14 variants) — one commit.
2. Fix the 2 MAP-BLOCKED map entries.
3. Per-file: repoint rule(s) → retire/re-anchor acceptance (if anchored) → delete legacy file.
4. Author the two guards; author `decommission-fill-later.md` (the 2 quarantine entries).
5. `validate-conventions` + persona CI green (coverage moved, not dropped).
6. **Scaffolding teardown (§f, final phase):** now that the sweep no longer needs them, delete the
   spent migration scaffolding (docs + map + classifier + oracle helpers + Y001/Y002 with re-anchor).
   Re-run `validate-conventions` + persona CI green to prove nothing that scaffolding gated is now
   unguarded.

**GREEN checkpoint:** the full diff — oracle-kill + repoint + re-anchor + legacy deletions **and the
§f scaffolding deletions** — is shown for operator confirm **before any file is removed**.
