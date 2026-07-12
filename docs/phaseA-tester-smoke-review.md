# Phase A review — tester smoke CA-rule atomization

Partial de-monolith of `src/atdd/tester/conventions/smoke.convention.yaml`.
Atomized ONLY the four core-agnostic `tester.smoke.*` rule ids into
`src/atdd/tester/conventions/nodes/`. All extension-bound rules
(`tester.smoke.pres`, the `tester.smoke.train-mounts-*` RENDER-001/002 rules,
`planner.smoke.synthetic-fixture-bypass`, `planner.smoke.feedback-loop-close-the-loop`)
were left untouched for Phase B.

## Atomized nodes

| node | severity | disposition | validator | introduced_in | aliases |
|------|----------|-------------|-----------|---------------|---------|
| `tester.smoke.no-collaborator-substitution` | 4 | suppress-and-clean | `test_smoke_no_collaborator_substitution::test_smoke_tests_do_not_substitute_collaborators` | 3.53.0 | — |
| `tester.smoke.operator-observable-assertion` | 3 | documentation-only | — (none in legacy) | 3.83.0 | — |
| `tester.smoke.cross-component-handoff-gap` | 3 | documentation-only | — (none in legacy) | 3.83.0 | — |
| `tester.smoke.harness-subprocess-failed-crash` | 3 | documentation-only | — (none in legacy) | 1.64.5 | TESTER-RENDER-003 |

## Pass 1 — extraction fidelity

- **Severity / disposition / introduced_in** preserved verbatim for all four.
- **Statement** = legacy `description` verbatim (block scalars flattened to a
  single string; no wording change).
- **Validator binding**: only `no-collaborator-substitution` carried a legacy
  `validator:`; it maps to `implementation.{type:validator, ref}`. The other
  three had **no** `validator:` field in the monolith and none `bind_rule()`s
  them — confirmed via grep — so they are authored without `implementation`
  (matching the documentation-only `tester.train.coverage` precedent). Adding a
  binding would have broken `test_rule_validator_binding`.
- **Rich fields preserved** (schema `additionalProperties: true`):
  - operator-observable `anti_patterns[]` → `content.counter_examples[]`.
  - cross-component `handoff_detection{}` → `content.handoff_detection{}`.
  - harness-subprocess classification (condition/detail/related #357) →
    `content.normative_text`.
  - All multi-line `fix_hint` blocks carried over verbatim.
- **Terms**: schema requires ≥1 `terms[]`; one definitional term synthesized per
  node from the rule's own prose (no new normative content).

## Pass 2 — de-monolith correctness

- Removed exactly the four atomized rule blocks:
  - `collaborator_substitution_rules` block (sole occupant → replaced with a
    migration-pointer comment).
  - `synthetic_fixture_anti_patterns.rules[]` items 2 & 3 (operator-observable,
    cross-component) — item 1 `planner.smoke.synthetic-fixture-bypass` retained.
  - `behavioral_render.rules[]` item 3 (harness-subprocess) — items 1 & 2
    (`train-mounts-but-the`, `train-mounts-but-the-1`) retained.
- Grep confirms 0 occurrences of the four ids as `id:` in the monolith, and the
  five EXT/leave ids still present.
- `test_no_duplicate_rule_representation` green (no rule represented in both
  monolith and nodes/).

## Pass 3 — graph wiring & orphans

- Hub-and-spoke added to `src/atdd/coach/graph/relationships.yaml`:
  hub `tester.smoke.no-collaborator-substitution` →`runs_alongside`→ each of the
  other three. All four ids now appear as relationship endpoints.
- `test_no_orphan_nodes` (clean baseline + fault-injection parity) green.
- **Semantic-mirror check**: no atomized rule mirrors an existing *core node*.
  `harness-subprocess-failed-crash` is conceptually adjacent to the
  `train-mounts-*` RENDER rules, but those remain in the monolith (EXT, Phase B)
  — there is no core node to `refines`, so no `refines` edge was added. No FLAG.

## Verification

```
pytest src/atdd/validators/conventions/coverage/test_no_orphan_nodes.py \
       src/atdd/validators/conventions/tests/test_sentinels.py \
       src/atdd/coach/validators/test_rule_validator_binding.py \
       src/atdd/coach/validators/test_no_duplicate_rule_representation.py \
       src/atdd/tester/validators/
→ 217 passed, 47 skipped, 1 xfailed (warnings are pre-existing coverage advisories)
```

`build_registry()` resolves all four canonical ids plus the `TESTER-RENDER-003`
alias; the hub's validator ref is intact.
