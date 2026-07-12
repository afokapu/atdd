# Phase A Review — atomize `tester.coverage` cluster to `nodes/`

Cluster: `tester.coverage` (file: `src/atdd/tester/conventions/coverage.convention.yaml`)
Pattern mirrored: the proven `tester.acceptance-violation` slice (commit `eaa47bea`).

## Pass 1 — Completeness

Every rule in the cluster has exactly one single-node file under `nodes/`, and the
monolith `rules:[]` block is gone.

| Rule id | Node file | Monolith block |
| --- | --- | --- |
| `tester.coverage.every-acceptance-criterion-must` | `nodes/tester.coverage.every-acceptance-criterion-must.convention.yaml` | removed |
| `tester.coverage.bidirectional-coverage-between-contracts` | `nodes/tester.coverage.bidirectional-coverage-between-contracts.convention.yaml` | removed |
| `tester.coverage.bidirectional-coverage-between-telemetry` | `nodes/tester.coverage.bidirectional-coverage-between-telemetry.convention.yaml` | removed |
| `tester.coverage.tracking-manifest-must-be` | `nodes/tester.coverage.tracking-manifest-must-be.convention.yaml` | removed |

`coverage.convention.yaml` now carries the header (`version`/`name`/`description`),
a migration-marker comment pointing at `nodes/`, and the retained descriptive
sections (`coverage_graph`, `exception_handling`, `test_discovery`, `rollout`) —
none of which are a `rules:[]` block, so they create no duplicate representation
(confirmed green by `test_no_duplicate_rule_representation`).

## Pass 2 — Fidelity

Field-by-field preservation against the legacy monolith:

- **every-acceptance-criterion-must**: name, statement(=description), alias
  `COVERAGE-TEST-3.1`, `disposition: documentation-only`, and the single
  `bidirectional` entry (direction/requirement/exceptions/validator
  `test_all_acceptances_have_tests`) all preserved. No severity declared in
  legacy → none added. Per the reverse-coherence gate, a documentation-only rule
  MUST NOT carry a top-level validator/`implementation` field → none added
  (the bidirectional entry's `validator` is sub-field metadata, not the rule
  binding).
- **bidirectional-coverage-between-contracts**: alias `COVERAGE-TEST-3.2`,
  `documentation-only`, both `bidirectional` directions preserved verbatim
  (`test_all_contracts_referenced`, `test_all_contract_refs_exist`, exceptions
  string intact). No top-level validator (documentation-only).
- **bidirectional-coverage-between-telemetry**: alias `COVERAGE-TEST-3.3`,
  `documentation-only`, both directions preserved (`test_all_telemetry_referenced`,
  `test_all_telemetry_refs_exist`). No top-level validator.
- **tracking-manifest-must-be**: alias `COVERAGE-TEST-3.4`, `severity: 3`,
  `disposition: strict` preserved. The legacy `requirement:` string is preserved
  as `content.normative_text`. `implementation.ref =
  test_hierarchy_coverage::test_telemetry_manifest_complete` preserved verbatim
  (the strict rule REQUIRES a bound validator; the target module binds the rule
  via a module-level `bind_rule("tester.coverage.tracking-manifest-must-be")`).

## Pass 3 — Graph + Green

- **No orphans**: all four node rule_ids are relationship endpoints in
  `src/atdd/coach/graph/relationships.yaml`. Mirroring the acceptance-violation
  hub pattern, `tester.coverage.every-acceptance-criterion-must` is the hub
  (`source_ref`) with `runs_alongside` edges to the other three
  (`bidirectional-coverage-between-contracts`,
  `bidirectional-coverage-between-telemetry`, `tracking-manifest-must-be`). The
  hub itself is an endpoint by being a `source_ref`.
- **Suite green** (no test edits were needed; `bind_rule` already reads `nodes/`
  via `single_node_rule_dict` since #1225):

```
217 passed, 47 skipped, 1 xfailed, 12 warnings in 95.71s (0:01:35)
```

  (The 12 warnings are pre-existing `COVERAGE-TEST-3.1/3.2a` Phase-2 advisory
  notices about acceptances/contracts lacking coverage — unrelated to this slice
  and present before it.)
