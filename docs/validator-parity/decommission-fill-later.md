# Decommission fill-later — quarantined legacy validators (#1365)

Legacy persona-validators whose convention variant does **not** provide independent real
coverage, so the **legacy test remains the only real coverage** and is **kept**. Recorded here
with an explicit reason so a later pass can revisit them (e.g. once the variant gains a real
fault-injection differential). These are intentionally excluded from the #1365 sweep.

Verdict authority: `docs/validator-parity/family-parity-report.md` (retired with the rest of the
scaffolding once these are resolved — until then the report's function-level / not-measurable
classifications stand).

| Legacy validator (KEPT) | Convention variant | Reason kept | Revisit-when |
|---|---|---|---|
| `src/atdd/planner/validators/test_theme_archetype_alignment.py` | `coherence/theme_archetype_alignment` | **function-level parity** — a same-file fault-injection differential is structurally impossible; parity was proven only at the scan-function level, so the variant is not independent real coverage. The rule `planner.theme.archetype-alignment` still binds to the legacy validator. | the variant gains a real on-disk fault-injection differential that catches an archetype/theme misalignment on the composed graph |
| `src/atdd/coach/validators/test_validate_contract_consumers.py` | `resolution/contract_consumer_resolution` | **not-measurable / legacy-hermetic** (`test_legacy_parity_not_measurable_via_injection`) — no real consume→contract reference data to inject against in this repo; the legacy test is hermetic (builds its own tmp fixture) and is the only coverage. | the repo grows real consume→contract references so a live-graph injection differential becomes measurable |

## Notes
- The oracle (`legacy_caught`/`assert_fault_parity`) legs in these two variants **were** dropped in
  the #1365 kill-oracle sweep (dual-maintenance removal); the legacy files themselves stay.
- Neither legacy file's rule was repointed — they remain bound to their legacy validators until revisited.
- Do NOT delete these two files in a "cleanup" pass without re-establishing real convention coverage first.

---

# Helper-coupled quarantine (#1365 partial sweep) — deferred deletions

These 9 legacy validators are **executing at parity** and their **rules were already repointed to the
convention variants** (enforcement has moved). They are **kept** only because surviving code still
**imports shared helper functions** from them (or a variant computes via an **in-process** import of
them). Deleting them now would break those importers — that is a focused **FOLLOW-UP** (extract the
shared helpers to a support module, repoint the importers), out of scope for the #1365 PR.

Each entry lists the exported symbol(s), the surviving importer(s), and the exact extract-work.

### Group A — sizing variants compute via in-process legacy import (extract the scan fns)

`src/atdd/validators/conventions/sizing/_parity.py` does
`import atdd.planner.validators.test_wagon_coupling_complexity as _coupling` /
`… test_wagon_separability as _separability` and calls `_coupling._scan(...)` etc. So the variant's
real computation lives in the legacy module. **Extract** the scan functions into a shared support
module (e.g. `conventions/sizing/_scan.py` or `planner/validators/_support/wagon_metrics.py`) that the
variant imports directly; then the legacy files can go.

| Legacy file (KEPT) | Exported symbols still needed | Consumer | Extract-work |
|---|---|---|---|
| `src/atdd/planner/validators/test_wagon_coupling_complexity.py` | `_scan`, `coupling_threshold` (+ imports `build_edges,load_manifests` from `test_no_cross_wagon_consume_cycle`) | `conventions/sizing/_parity.py::legacy_coupling_scan` | move `_scan`/`coupling_threshold` → shared module; variant imports it; drop legacy |
| `src/atdd/planner/validators/test_wagon_separability.py` | separability `_scan` | `conventions/sizing/_parity.py::legacy_separability_scan` | same as above |
| `src/atdd/planner/validators/test_no_cross_wagon_consume_cycle.py` | `build_edges`, `load_manifests` | `test_wagon_coupling_complexity.py` (above) + `conventions/acyclicity/_parity.py` (subprocess nodeid string) | move `build_edges`/`load_manifests` → shared graph-edge support module; repoint the coupling importer |

### Group B — legacy exports helper functions imported by surviving application-layer tests

| Legacy file (KEPT) | Exported symbols | Surviving importer(s) | Extract-work |
|---|---|---|---|
| `src/atdd/planner/validators/test_no_orphan_nodes.py` | `orphan_nodes` (+ `node_ids`, `referenced_node_ids`, `_excluded`) | `tests/test_c008_unit_001_orphan_detection.py` | move node-scan helpers → `planner/validators/_support/orphan_scan.py`; repoint importer; drop legacy |
| `src/atdd/planner/validators/test_smoke_synthetic_fixture_bypass.py` | meta-walker helpers | `tests/test_l002_smoke_001…`, `tests/test_l002_unit_001…`, `tests/test_e028_unit_004…`, `…unit_005…`, `…integration_001…` (5 importers) | extract meta-walker fns → support module; repoint 5 importers |
| `src/atdd/planner/validators/test_wmbt_has_smoke_acceptance.py` | `_RULE`, `_SMOKE_URN_RE`, `evaluate_wmbt_smoke_coverage`, `extract_acceptance_urns`, `has_smoke_urn` | `tests/test_wmbt_has_smoke_acceptance_helpers.py` | extract smoke-URN helpers → support module; repoint importer |
| `src/atdd/planner/validators/test_feedback_loop_smoke_closes_the_loop.py` | `_RULE`, `_SMOKE_URN_RE`, `acceptance_has_close_the_loop`, `evaluate_feedback_loop_coverage`, `iter_feedback_loop_features` | `tests/test_feedback_loop_smoke_closes_the_loop_helpers.py` | extract feedback-loop helpers → support module; repoint importer |
| `src/atdd/planner/validators/test_dispatch_registry.py` | `check_composite_key_exceptional` | `tests/test_e006_smoke_001_executable_train_rules_bound.py` | extract dispatch helper → support module; repoint importer |
| `src/atdd/coach/validators/test_fix_hint_completeness.py` | `audit_c1_placeholder_resolution`, `audit_c2_no_deprecation_contradiction`, `build_deprecation_registry`, `load_negative_exemplars` | `tests/test_fix_hint_completeness_helpers.py` | extract fix-hint audit helpers → support module; repoint importer |

### Group C — binding-family: the legacy validator IS the `bind_rule` emitter (3)

The `emitted_identity_roundtrip` binding template detects a broken declaration→implementation
binding by observing whether the rule's id is **emitted via `bind_rule(<id>)` at import time**.
Only the legacy validator calls `bind_rule` — the convention variant *tests* the binding but does
not *provide* it. So these rules **cannot be repointed to the variant** (doing so makes the
roundtrip fault-injection vacuous — caught by the full `validate-conventions` run) and the legacy
file **cannot be deleted** without relocating the `bind_rule` calls. Their rules remain bound to
the legacy validator; the convention variant continues to prove parity.

| Legacy file (KEPT) | `bind_rule` emissions | Consumer | Extract-work |
|---|---|---|---|
| `src/atdd/coach/validators/test_commit_trailers_binding.py` | `bind_rule("coach.commit-trailers.{phase,wmbt-urn,agent-id,issue}-required")` | the 4 rules' binding + `binding/commit_trailers_rule_binding` roundtrip | relocate the `bind_rule` calls to a non-test binder module the rule can point at, then delete |
| `src/atdd/coach/validators/test_e001_unit_001_spawn_cli_launches_session.py` | `bind_rule("coach.spawn.atdd-spawn-cli")` | `coach.spawn.atdd-spawn-cli` + `binding/spawn_cli_rule_binding` | same |
| `src/atdd/coach/validators/test_no_hardcoded_rule_severity.py` | `bind_rule("coach.rule-id.no-hardcoded-rule-severity")` | that rule + `binding/no_hardcoded_rule_severity` | same |

**Follow-up issue shape:** "extract the shared helper functions AND the `bind_rule` emitters out of
the 12 quarantined legacy validators into support/binder modules, repoint the importers + rule
bindings, then delete the 12 legacy files (completing the #1207 sweep)." Small, mechanical,
well-scoped. (The binding 3 are a distinct sub-task: relocate `bind_rule` emitters.)

## Scaffolding NOT torn down (deferred — still referenced by the remaining 9)
Because 9 legacy validators remain, the parity scaffolding is still in use and its teardown (#1365 §f)
is **deferred to the follow-up that resolves the 9**:
- `scripts/decommission_manifest.py` + `docs/validator-parity/legacy-validator-map.yaml` — still
  describe the 9 pending files; Y001/Y002 still guard them.
- Y001 (`test_y001_no_unsafe_deletion`) / Y002 (`test_y002_decommission_preflight_classifier`) — still
  needed while the 9 remain.
- `_support` oracle helpers (`legacy_caught`/`legacy_catches`/`assert_fault_parity`) + parity-harness
  tests (`tests/test_sentinels.py`, `tests/test_catch_matrix.py`) — still reference legacy nodeids.
- `family-parity-report.md` + migration reports — verdict authority for the remaining 9.

The permanent **Y003 guards are kept** (they are not scaffolding).
