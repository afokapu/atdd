# Phase A core-atomization review — cluster `tester misc`

Slice: atomize 5 core-agnostic tester rules (4 monolith convention files) into
single-node files under `src/atdd/tester/conventions/nodes/`, mirroring the
proven `tester.acceptance-violation.*` slice (#1225 / commit eaa47bea).

## Pass 1 — Completeness (every listed rule = 1 node, monolith block gone)

| Rule id | Node file | Monolith `rules:` block removed |
|---|---|---|
| `tester.security.auth` | `nodes/tester.security.auth.convention.yaml` | ✅ |
| `tester.security.input` | `nodes/tester.security.input.convention.yaml` | ✅ |
| `tester.test-isolation.no-polluting-patterns` | `nodes/tester.test-isolation.no-polluting-patterns.convention.yaml` | ✅ |
| `tester.telemetry.emit` | `nodes/tester.telemetry.emit.convention.yaml` | ✅ |
| `tester.train.coverage` | `nodes/tester.train.coverage.convention.yaml` | ✅ |

- 5 rules → 5 nodes, 1:1. All authored via
  `atdd author convention-node --core --role tester`.
- `grep -nE '^rules:'` over all four touched monolith files → **NONE**. Each
  `rules:` block was replaced by a migration-marker comment matching the shape
  used in `acceptance-violation.convention.yaml` (points readers to `nodes/`).
- Non-rule body of each monolith file (the `validators:` SPEC block in
  security, the full telemetry tracking-plan body, the train journey-test body,
  the test-isolation header/description) is preserved untouched.

## Pass 2 — Fidelity (severity / disposition / statement / fix_hint / ref / aliases)

| Rule | severity | disposition | aliases | introduced_in | impl ref | fix_hint |
|---|---|---|---|---|---|---|
| security.auth | 4 ✅ | documentation-only ✅ | TESTER-SECURITY-AUTH-001 ✅ | 1.67.0 ✅ | (none in source) ✅ | (none) |
| security.input | 4 ✅ | documentation-only ✅ | TESTER-SECURITY-INPUT-001 ✅ | 1.67.0 ✅ | (none in source) ✅ | (none) |
| test-isolation.no-polluting-patterns | 4 ✅ | strict ✅ | (none) | (none) | `test_no_polluting_patterns::test_repo_has_no_pollution_patterns` ✅ | full multi-line recipe preserved verbatim ✅ |
| telemetry.emit | 3 ✅ | documentation-only ✅ | TESTER-TELEMETRY-EMIT-001 ✅ | 1.67.0 ✅ | (none in source) ✅ | (none) |
| train.coverage | 2 ✅ | documentation-only ✅ | TESTER-TRAIN-COVERAGE-001 ✅ | 1.67.0 ✅ | (none in source) ✅ | (none) |

- `statement` on each node = the source rule `description` verbatim.
- Only `tester.test-isolation.no-polluting-patterns` carried a `validator` ref
  (`bind_rule` confirmed in `test_no_polluting_patterns.py:48`, test fn at
  `:244`); preserved exactly as `implementation.{type,ref}`. Its multi-line
  `fix_hint` recipe is preserved character-for-character under `content.fix_hint`.
- The other four rules are documentation-only with no validator binding in the
  monolith — faithfully carried over with NO fabricated `implementation`/
  `fix_hint`. No field invented; no assertion weakened.
- `source:` block on every node records `legacy_path` (its origin convention
  file), `legacy_section: rules`, `legacy_rule_id`, `extraction_mode:
  high_fidelity`.
- A faithful single `terms:` entry was added per node (required by `atdd
  author` §5.2); term ids are semantic snake_case (§D005).

## Pass 3 — Graph + green (no orphans, suite green)

- All 5 new node rule_ids wired into `src/atdd/coach/graph/relationships.yaml`
  as a `runs_alongside` cluster, mirroring the acceptance-violation hub shape:
  hub `tester.security.auth` → {`security.input`, `test-isolation.no-polluting-patterns`,
  `telemetry.emit`, `train.coverage`}. 8 endpoint references total (hub ×4 as
  `source_ref`, each target ×1) — every new node is a relationship endpoint, no
  orphans.
- Verification suite (no test needed updating — no test read the removed
  monolith `rules:` blocks directly):

```
PYTHONPATH=src .../python -m pytest \
  src/atdd/validators/conventions/coverage/test_no_orphan_nodes.py \
  src/atdd/validators/conventions/tests/test_sentinels.py \
  src/atdd/coach/validators/test_rule_validator_binding.py \
  src/atdd/coach/validators/test_no_duplicate_rule_representation.py \
  src/atdd/tester/validators/ -p no:cacheprovider -q

217 passed, 47 skipped, 1 xfailed, 12 warnings in 95.72s (0:01:35)
```

  0 failures. The 12 warnings are pre-existing `COVERAGE-TEST-3.x` advisories
  unrelated to this slice. `test_no_orphan_nodes` (clean-baseline = 0),
  `test_sentinels`, `test_rule_validator_binding`, and
  `test_no_duplicate_rule_representation` all pass — confirming the registry now
  reads the 5 rules from `nodes/`, binding is intact, and there is no
  duplicate representation between monolith and `nodes/`.
