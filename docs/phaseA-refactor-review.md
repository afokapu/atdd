# Phase A review — coder.refactor cluster (PARTIAL de-monolith)

Atomized the **3 core-agnostic** rules of `src/atdd/coder/conventions/refactor.convention.yaml`
into single-node `nodes/` files via `atdd author convention-node --core --role coder`.
The stack-specific `complexity-*` / `quality-*` / `nplus1` rules were **left in the
monolith untouched** (extension-bound; migrate in Phase B).

Rules atomized:
- `coder.refactor.coach-ratchet-pres`   (was under `ratchet_smoke_gate.rules`)
- `coder.refactor.composition-consumer` (was top-level `rules:[]`)
- `coder.refactor.composition-root`      (was top-level `rules:[]`)

## Pass 1 — extraction fidelity (high_fidelity)

| field | coach-ratchet-pres | composition-consumer | composition-root |
|-------|--------------------|----------------------|------------------|
| statement (= description verbatim) | ✓ | ✓ | ✓ |
| severity | 3 ✓ | 3 ✓ | 3 ✓ |
| disposition | advisory ✓ | strict ✓ | strict ✓ |
| aliases | COACH-RATCHET-PRES-001 ✓ | REFACTOR-COMPOSITION-CONSUMER-001 ✓ | REFACTOR-COMPOSITION-ROOT-001 ✓ |
| introduced_in | (none in source) | 1.67.0 ✓ | 1.67.0 ✓ |
| implementation.ref (= validator) | test_presentation_ratchet_requires_smoke::test_detects_25pct_reduction_in_presentation_tsx ✓ | test_composition_completeness::test_composition_convention_exists_and_has_required_sections ✓ | (same) ✓ |
| source.* | legacy_path + legacy_section=`ratchet_smoke_gate.rules` + legacy_rule_id + high_fidelity ✓ | legacy_section=`rules` ✓ | legacy_section=`rules` ✓ |

`coach-ratchet-pres` carried rich gate config beyond the standard schema. Preserved
losslessly into node fields rather than dropped:
- `rationale:` (+ the past-incident note from the monolith header comment) → node `rationale:`
- `applies_to` + `threshold` (0.20) + `gate` (Blocks SMOKE→REFACTOR …) → `content.normative_text`
- `triggers[]` (incl. "deleted file = 100% reduction, Decision #4") → `content.constraints`
- `record_command` + `evidence.location` (`.atdd/smoke-evidence/<issue>.yaml`, gitignored) → `content.fix_hint`
- `title` was identical to `description`; folded into `name`/`statement`, not duplicated.

The two composition rules had no `fix_hint`/`recipe` in the monolith; a concise,
faithful `content.fix_hint` was synthesized from each rule's own description (no new
normative scope introduced).

## Pass 2 — partial de-monolith correctness

- Only the 3 listed rule blocks removed from `refactor.convention.yaml`.
- The single-rule `ratchet_smoke_gate:` wrapper held *only* `coach-ratchet-pres`, so the
  whole wrapper was removed and replaced with a moved-to-`nodes/` comment marker.
- The 2 composition entries removed from the tail of the top-level `rules:[]`; a comment
  marker notes the move and that complexity-*/quality-*/nplus1 stay until Phase B.
- **No migration marker claiming the whole file moved** — it didn't; 18 EXT rules remain.
- `test_no_duplicate_rule_representation` green: no rule_id is in both monolith and nodes/.

## Pass 3 — graph wiring / no orphans

- All 3 new rule_ids are relationship endpoints in `relationships.yaml`:
  - hub `coder.refactor.composition-root` → `composition-consumer` (runs_alongside)
  - hub `coder.refactor.composition-root` → `coach-ratchet-pres` (runs_alongside)
- `test_no_orphan_nodes` green (clean baseline 0). `test_rule_validator_binding` green
  (bind_rule resolves all 3 from nodes/). `test_sentinels` green.

## ⚠ Flag for overseer (STEP 4)

`composition-consumer` and `composition-root` **share the same validator binding**
(`test_composition_completeness::test_composition_convention_exists_and_has_required_sections`).
This is faithful to the monolith (both rules bound to that one validator there too) — they
are two distinct facets of composition-completeness (per-layer-consumer vs. root-reaches-all),
not a mirror/restatement, so each keeps its own rule_id. Wired as `runs_alongside` peers
(not `refines`). No cross-cluster duplicate detected for `coach-ratchet-pres`.

## Verification

`PYTHONPATH=src … pytest test_no_orphan_nodes test_sentinels test_rule_validator_binding
test_no_duplicate_rule_representation src/atdd/coder/validators/` → **197 passed, 112
skipped, 0 failed** (warnings are pre-existing advisory disposition notices, unrelated).
