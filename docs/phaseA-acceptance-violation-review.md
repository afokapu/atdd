# Phase A Review — `tester.acceptance-violation.*` atomization

Atomizes the monolith `src/atdd/tester/conventions/acceptance-violation.convention.yaml`
(`rules:[]` of 9 rules) into 9 single-node files under `nodes/`, via
`atdd author convention-node --core --role tester`. Node 1
(`acceptance-must-be-measurable`) was the pre-existing seed; nodes 2–9 mirror its shape.

## Pass 1 — COMPLETENESS

9 nodes exist under `src/atdd/tester/conventions/nodes/`, each a 1:1 map of a monolith rule.
No rule dropped, none invented.

| # | Monolith rule id | Node file |
|---|------------------|-----------|
| 1 | acceptance-must-be-measurable | `tester.acceptance-violation.acceptance-must-be-measurable.convention.yaml` (seed) |
| 2 | acceptance-must-declare-phase | `…acceptance-must-declare-phase.convention.yaml` |
| 3 | disposition-must-not-be-declared | `…disposition-must-not-be-declared.convention.yaml` |
| 4 | validator-binding-must-be-bidirectional | `…validator-binding-must-be-bidirectional.convention.yaml` |
| 5 | security-rule-must-have-acceptance-ref-resolved | `…security-rule-must-have-acceptance-ref-resolved.convention.yaml` |
| 6 | metric-implementation-must-exist | `…metric-implementation-must-exist.convention.yaml` |
| 7 | hermetic-fake-must-declare-contract | `…hermetic-fake-must-declare-contract.convention.yaml` |
| 8 | hermetic-live-smoke-required-must-have-paired-smoke-acceptance | `…hermetic-live-smoke-required-must-have-paired-smoke-acceptance.convention.yaml` |
| 9 | live-smoke-acceptance-must-execute | `…live-smoke-acceptance-must-execute.convention.yaml` |

The monolith `rules:[]` block is **gone** — `acceptance-violation.convention.yaml` retains only
`schema_version` / `convention_id` / `name` / `description` plus a comment migration marker
pointing the registry to `nodes/` (mirroring the `planner.relationship.no-orphan-nodes` /
`planner.plan.*` decommission precedent, which strip the inline `rules:` list entirely after
#1225 made the registry read `nodes/`). `test_no_duplicate_rule_representation` passes,
confirming there is exactly one representation per rule.

## Pass 2 — FIDELITY

Each node preserves severity / disposition / statement(=description) / fix_hint /
implementation.ref from its source rule (diffed against the original monolith).

| Rule | severity (monolith→node) | disposition | implementation.ref (verbatim from `validator:`) |
|------|--------------------------|-------------|--------------------------------------------------|
| acceptance-must-be-measurable | 4→4 | strict | `test_acceptance_measurable::test_every_acceptance_has_enforcement` |
| acceptance-must-declare-phase | 4→4 | strict | `test_acceptance_phase::test_every_acceptance_declares_phase` |
| disposition-must-not-be-declared | 3→3 | strict | `test_acceptance_disposition::test_no_disposition_in_repo_yaml` |
| validator-binding-must-be-bidirectional | 3→3 | strict | `test_repo_validator_binding::test_validator_binding_is_bidirectional` |
| security-rule-must-have-acceptance-ref-resolved | 4→4 | strict | `test_security_ref_binding::test_every_abuse_case_resolves` |
| metric-implementation-must-exist | 4→4 | strict | `test_metric_implementation::test_every_signal_metric_has_compute_function` |
| hermetic-fake-must-declare-contract | 4→4 | strict | `test_hermetic_integration_contract::test_no_undeclared_hermetic_fakes` |
| hermetic-live-smoke-required-must-have-paired-smoke-acceptance | 4→4 | strict | `test_hermetic_live_smoke_pairing::test_hermetic_live_smoke_required_is_paired` |
| live-smoke-acceptance-must-execute | 4→4 | strict | `test_live_smoke_execution::test_every_live_smoke_acceptance_executed` |

- **statement** = the monolith `description` verbatim for every node.
- **fix_hint** preserved into `content.fix_hint` (single-line, semantics intact); the `recipe:`
  pointer preserved as `content.operational_guidance: "recipe: <name>"`.
- Each node carries `source:` provenance (`legacy_path` / `legacy_section: rules` /
  `legacy_rule_id` / `extraction_mode: high_fidelity`) plus a synthesized snake_case `term`
  (CLI-required; `T1/T2`-style numbered/hyphenated term_ids are rejected by §D005).

## Pass 3 — GRAPH + GREEN

All 9 rule_ids are relationship endpoints in `src/atdd/coach/graph/relationships.yaml` — none
orphaned. Authored via `atdd author relationship --core`: a hub-and-spoke of 8
`runs_alongside` edges from `acceptance-must-be-measurable` to each of the other 8
(`foundation: start_to_start`, `constraint: mandatory`, `control: internal`,
`strength: minor`, `confidence: 1.0`). 16 endpoint references = hub (×8 source) + 8 distinct
targets, covering all 9 distinct rule_ids.

One legacy holdout (`test_hermetic_integration_fixtures.py::test_e006_unit_001`) read the
inline `rules:[]` block to confirm the two hermetic rule_ids were declared. It was updated to
read the decomposed node form (with inline-block backward-compat) — the faithful migration;
retaining the inline block would have violated STEP 2 and tripped no-duplicate-representation.

Verification suite (`test_no_orphan_nodes` + `test_sentinels` +
`test_rule_validator_binding` + `test_no_duplicate_rule_representation` + all
`src/atdd/tester/validators/`):

```
217 passed, 47 skipped, 1 xfailed, 12 warnings in 96.85s (0:01:36)
```

`test_clean_baseline_is_zero` (no orphan nodes) and `test_no_duplicate_rule_representation`
both green.
