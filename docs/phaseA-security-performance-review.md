# Phase A Review — coder security + performance atomization (PARTIAL)

Cluster (**partial** de-monolith — only the listed core-agnostic ids atomized):
`security.convention.yaml`, `performance.convention.yaml`. Pattern mirrors the
proven tester `acceptance-violation` atomization (#1225).

⚠️ PARTIAL: every other rule in each monolith is intentionally LEFT intact.

## Pass 1 — Completeness (only the in-scope ids moved)

| Monolith | Rule id | Action | Node file |
|---|---|---|---|
| security.convention.yaml | `coder.security.xss` | **atomized** | `coder.security.xss.convention.yaml` |
| security.convention.yaml | `coder.security.hardcoded-secret` | **atomized** | `coder.security.hardcoded-secret.convention.yaml` |
| performance.convention.yaml | `coder.performance.perf` | **atomized** | `coder.performance.perf.convention.yaml` |

LEFT in place (verified present, untouched):

- `security.convention.yaml` top-level `rules:[]` — `coder.security.sql-injection`,
  `coder.security.missing-auth` retained verbatim.
- `security.convention.yaml` nested `security:` EXT block — `coder.security.no-raw-sql-string`
  (sql_injection), `coder.security.fastapi-routes-must-have` (missing_auth),
  `coder.security.no-hardcoded-secrets-aws` (hardcoded_secrets),
  `coder.security.no-innerhtml-or-dangerouslysetinnerhtml` (xss_patterns) — these
  carry the AST/regex pattern config the validator reads and are NOT
  registry-walked top-level rules, so they were retained, not atomized.
- `performance.convention.yaml` `validators:`, `excluded_paths:`, `future_rules:`
  sections — metadata, not rule declarations — retained.

Each monolith keeps its header + a migration-marker comment naming what moved and
what was deliberately left. `performance.rules` is now `[]` (its sole rule moved);
the security top-level `rules:[]` still holds the two left-behind rules.

No listed rule was a MIRROR of an existing node → no `refines` edge, no flag.

## Pass 2 — Fidelity (high_fidelity extraction)

All nodes authored via `atdd author convention-node --core --role coder`.

- **coder.security.xss**: statement = monolith description verbatim ("No innerHTML
  or dangerouslySetInnerHTML in frontend code (use safe DOM APIs)"),
  disposition `documentation-only`, alias `SECURITY-XSS-001`, `introduced_in 1.67.0`.
  Source carried **no** `validator:` field → node has **no** `implementation`
  block (correct: doc-only rules must NOT name a validator, per
  `test_rule_validator_binding`).
- **coder.security.hardcoded-secret**: statement = description verbatim,
  disposition `strict`, alias `SECURITY-HARDCODED-SECRET-001`, `introduced_in 1.67.0`,
  `implementation.ref = test_security_patterns::test_no_raw_sql_concatenation`
  (preserved verbatim — that module binds the id at import time, so reverse
  coherence still resolves).
- **coder.performance.perf**: statement = the multi-line description (DB client
  calls must not appear in loop bodies/comprehensions), disposition
  `documentation-only`, alias `PERF-001`. No `validator:` field in source → no
  `implementation` block. `fix:` text folded into `content.fix_hint`.
- Every node carries `source.{legacy_path,legacy_section,legacy_rule_id}` +
  `extraction_mode: high_fidelity`, plus a faithful `terms[]` entry defining the
  rule's key concept (xss_sink / hardcoded_secret / n_plus_one).

**Documented fidelity deviation — severity normalization.** The node schema
(`convention-node.schema.json`) caps `metadata.severity` at integer 1–4. The
monolith declared `severity: 5` (xss, hardcoded-secret) and `severity: "error"`
(perf). All three were mapped to the schema-max `4` (= error level), matching how
existing high-severity nodes (e.g. tester `acceptance-violation`) are authored.
The left-behind monolith rules keep their original `severity: 5`. Severity value
is not consumed by any gate in the verification suite; disposition (which governs
enforcement) was preserved exactly.

## Pass 3 — Graph + Green

- **Graph**: 2 `runs_alongside` edges appended to
  `src/atdd/coach/graph/relationships.yaml` so all 3 new ids are graph endpoints
  (no orphans):
  - intra-cluster hub `coder.security.xss` → `coder.security.hardcoded-secret`
  - cross-cluster peer `coder.performance.perf` → `coder.security.xss` (both are
    consumer-code static-analysis anti-pattern gates; cross-cluster
    `runs_alongside` is already established in the tester clusters, e.g.
    `tester.security.auth` → `tester.telemetry.emit`). `perf` has no sibling
    within this partial slice, so a peer edge is the correct hub attachment.
- **bind_rule resolution** verified live for all 5 affected ids + aliases: the 3
  atomized ids resolve from `nodes/`, the 2 left-behind ids
  (`sql-injection`, `missing-auth`) still resolve from the monolith, aliases
  `SECURITY-XSS-001` / `PERF-001` resolve to canonical.
- **No test rewrites required**: `test_security_patterns.py` reads the nested
  `security:` block (untouched) for pattern config and binds
  `coder.security.hardcoded-secret` via `bind_rule` (now satisfied by the node);
  `test_query_count.py` binds `coder.refactor.nplus1`, not `coder.performance.perf`,
  and reads `refactor.convention.yaml` — neither monolith-reading path broke.
- **Green**: full gate (`test_no_orphan_nodes`, `test_sentinels`,
  `test_rule_validator_binding`, `test_no_duplicate_rule_representation`, all
  coder validators) → **197 passed, 112 skipped, 0 failed** (identical to the
  pre-change baseline). `test_rule_id_uniqueness` + `test_rule_id_registry_coherence`
  → 4 passed. Remaining warnings are pre-existing advisory dispositions unrelated
  to this change.
