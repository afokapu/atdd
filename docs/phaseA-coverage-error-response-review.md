# Phase A Review — coder coverage + error-response atomization

Cluster (all core-agnostic → full de-monolith): `coverage.convention.yaml`,
`error-response.convention.yaml`. Pattern mirrors the proven tester
`acceptance-violation` / `coverage` atomization (#1225).

## Pass 1 — Completeness

Every rule from each monolith `rules:[]` block became exactly one single-node
file under `src/atdd/coder/conventions/nodes/`:

| Monolith | Rule id | Node file |
|---|---|---|
| coverage.convention.yaml | `coder.coverage.every-feature-must-have` | `coder.coverage.every-feature-must-have.convention.yaml` |
| coverage.convention.yaml | `coder.coverage.every-implementation-must-have` | `coder.coverage.every-implementation-must-have.convention.yaml` |
| error-response.convention.yaml | `coder.error-response.bare-string` | `coder.error-response.bare-string.convention.yaml` |
| error-response.convention.yaml | `coder.error-response.code-format` | `coder.error-response.code-format.convention.yaml` |

- No stack-specific / EXT rules existed in either file → nothing skipped or
  flagged. (`error-response.convention.yaml` also carries a `legacy_rules:`
  prose dict — ERR-01..ERR-05 — which is *documentation*, NOT a
  registry-walked `rules:[]` list; it was retained, not atomized.)
- Both monoliths now contain **no** `rules:[]` block (grep-verified); each
  keeps its header + descriptive sections + migration-marker comment whose
  shape mirrors `acceptance-violation.convention.yaml` / tester
  `coverage.convention.yaml`.

## Pass 2 — Fidelity (high_fidelity extraction)

All nodes authored via `atdd author convention-node --core --role coder`.
Field-by-field preservation:

- **every-feature-must-have**: name, statement(=description verbatim),
  severity 3, disposition strict, alias `COVERAGE-CODE-4.1`, validator ref
  `test_hierarchy_coverage::test_all_features_have_implementations`,
  `requirement` → `content.normative_text`, `exceptions` → `content.exceptions`.
- **every-implementation-must-have**: severity 3, strict, alias
  `COVERAGE-CODE-4.2`, validator
  `test_hierarchy_coverage::test_all_implementations_have_tests`,
  `requirement` → `content.normative_text`.
- **bare-string**: severity 4, strict, alias `ERROR-BARE-STRING-001`,
  `introduced_in: 1.67.0` preserved in metadata, validator
  `test_error_response_compliance::test_error_response_contract_exists`.
  Source had no `name:` → concise faithful name "No bare string error detail".
- **code-format**: severity 4, strict, alias `ERROR-CODE-FORMAT-001`,
  `introduced_in: 1.67.0`, same validator ref; statement = description verbatim
  (regex `^[A-Z][A-Z0-9_]+$` preserved).
- Every node carries `source.{legacy_path,legacy_section,legacy_rule_id}` +
  `extraction_mode: high_fidelity`. No invented severities/dispositions; no
  recipe existed in source → `operational_guidance` correctly omitted.

## Pass 3 — Graph + Green

- **Graph**: 2 intra-cluster `runs_alongside` hub edges appended to
  `src/atdd/coach/graph/relationships.yaml`, mirroring the tester clusters:
  - hub `coder.coverage.every-feature-must-have` → `…every-implementation-must-have`
  - hub `coder.error-response.bare-string` → `…code-format`
  All 4 new rule_ids appear as graph endpoints (6 ref occurrences). No orphans
  (`test_no_orphan_nodes` green).
- **Test update (not weakened)**: `test_error_response_convention_exists`
  required a `rules` section in the monolith; rewritten to require the two
  descriptive sections in the monolith **and** assert each rule now resolves to
  a decomposed node under `nodes/` carrying the correct `rule_id` — a strictly
  stronger check.
- **Green**: full gate (no_orphan_nodes, sentinels, rule_validator_binding,
  no_duplicate_rule_representation, all coder validators) →
  **197 passed, 112 skipped, 0 failed**. Remaining warnings are pre-existing
  advisory dispositions unrelated to this change.
