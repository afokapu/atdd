# Single-node ingestion + `implementation.ref` normalization — findings (#1212 a-fix)

Closes the (a-fix) blocker in `author-engine-reconciliation-plan.md`: the
convention-graph engine now node-ifies the single-node convention files emitted by
`atdd author` (`<role>/conventions/nodes/<rule_id>.convention.yaml`), and the binding
sentinel resolves the heterogeneous `implementation.ref` forms honestly.

## What changed

- `_support/graph_loader.py` — **two-pass** rule ingestion. Pass 1 loads `rules:[]`
  blocks (legacy representation). Pass 2 loads single-node files (top-level `rule_id`,
  no `rules:` block), mapping `validator = implementation.ref`, and **skips any
  `rule_id` already loaded from a block** (migration overlap = the same rule in two
  representations, not a duplicate). Also added a per-function index of validator
  modules (`def <name>` → owning stem) so bare-function refs can resolve.
- `_support/sentinels.py` — `declaration_to_implementation_binding` now resolves the
  three ref forms via `_binding_ref_resolves` (see below). No single-node node is
  exempted from binding.

## Measured baseline (real repo, `load_composed_graph(".")`)

| metric                                   | before | after |
|------------------------------------------|--------|-------|
| rule nodes (`g.rules()`)                 | 152    | 269   |
| total nodes                              | 732    | 849   |
| `scoped_identifier_uniqueness` violations| 0      | 0     |
| `declaration_to_implementation_binding`  | 0      | 0     |
| `rule_validator_roundtrip` violations    | 0      | 0     |

(The plan's "~270" estimate; the exact ingested corpus is 269 because the 158 authored
single-node files overlap the blocks by the migration-mirrored set, leaving +117 new
rule nodes over the 152 blocks-only baseline.)

## The heterogeneous `implementation.ref` forms — honest classification

Of the 25 single-node files carrying an `implementation.ref`, three resolution forms
appear. All resolve to a **real, enforced validator** — none required suppression:

1. **`module::function`** (the majority, e.g.
   `test_theme_must_be_canonical::test_every_wagon_theme_is_canonical`). Resolves iff
   the file stem is a known validator stem. Unchanged from legacy behaviour.

2. **rule-id cross-reference** —
   - `planner.smoke.feedback-loop-close-the-loop` (referenced by
     `planner.feature.feedback-loop-close-the-loop`)
   - `tester.acceptance-violation.hermetic-fake-must-declare-contract` (referenced by
     `planner.acceptance.hermetic-fake-contract` and `…boundary-kind-vocabulary`)

   These point at another rule rather than a file. They resolve when the referenced
   rule is genuinely enforced — proven either by (a) a loaded rule node whose own ref
   resolves, or (b) a **validator module calling `bind_rule(<ref>)`** (the `emits`
   index). The feedback-loop target's declaration lives in a *nested* `rules:` block
   (`smoke.convention.yaml::feedback_loop_rules.rules`) that the loader does not
   node-ify, but its validator `test_feedback_loop_smoke_closes_the_loop.py` calls
   `bind_rule("planner.smoke.feedback-loop-close-the-loop")` — so the binding is real,
   just indirected. Path (b) confirms it without widening the loader to nested blocks.

3. **bare function name** — `test_train_files_exist_for_registry_entries` (referenced
   by `planner.train.registry`). Resolves to the validator module that defines it
   (`def test_train_files_exist_for_registry_entries` in
   `src/atdd/planner/validators/test_train_validation.py`) via the function index.

## Unresolvable refs

**None.** Every single-node `implementation.ref` in the repo resolves to a real
validator under one of the three forms above. Had any failed, it would have been left
as a live binding violation (a real unbound-implementation defect), not exempted.

## Deliberately out of scope

The loader still ingests rules only from **top-level** `rules:[]` blocks and the
single-node files — it does **not** node-ify *nested* `rules:` blocks (29 exist, e.g.
under `smoke.convention.yaml`). Expanding those is a separate change that would shift
the uniqueness/roundtrip baselines; here it is unnecessary because cross-refs into
nested-block rules resolve via the `bind_rule` emit index.
