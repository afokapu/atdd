# URN Spec v3 — Component + Test URNs
Status: Draft (Proposal)

## 1. Problem
We want a consistent rule that all production code files carry a `component:` URN and that test files carry explicit `test:` URNs. The current ATDD schema is feature-scoped for `component:` and test URNs can be auto-generated from paths, which makes resolution non-deterministic in large repos. Train infrastructure code also lives outside wagon/feature directories and is not expressible with current resolver mapping.

## 2. Goals
1. Every production code file has a `component:` URN.
2. Every test file has an explicit `test:` URN (no reliance on auto-generation).
3. Support orchestration/entrypoint code that sits above the 4 layers.
4. Allow train infrastructure files to be expressed with `component:` URNs.
5. Use a single train URN format: `train:{train_id}` (theme is metadata, not part of the URN).

## 3. Non-Goals
1. Replacing plan URNs (`wagon:`, `feature:`) with code URNs.
2. Changing other URN families (contract, telemetry, etc.) beyond this spec.

## 4. Principles
1. `component:` = production code files.
2. `train:`, `wagon:`, `feature:` = plan artifacts only.
3. `acc:` = acceptance criteria (traceability target, not test identity).
4. `assembly` is a layer for orchestration/entrypoints above the 4 layers.
5. Tests declare outcomes (acc/wmbt) in RED; components declare `Tested-By` in GREEN/REFACTOR.
6. Trains are strictly linear: sequences are steps only (no loops/routes/branching).

## 5. URN Families
- `wagon:{slug}` — wagon plan definition (YAML)
- `feature:{wagon}:{feature}` — feature plan definition (YAML)
- `train:{train_id}` — train plan definition (YAML)
- `component:{...}` — production code
- `test:{...}` — test identity
- `acc:{...}` — acceptance criteria

Train ID format: `{train_id}` = `NNNN-kebab-case` (pattern `^\d{4}-[a-z0-9-]+$`), where the digits encode theme/category/variation as documented in train conventions.

Scope note: other URN families (wmbt, contract, telemetry, table, migration, endpoint, topic, etc.) are unchanged and out of scope for this spec.

## 6. Component URNs
### 6.1 Standard 4-Layer Components
```
component:{wagon}:{feature}:{name}:{side}:{layer}
```
- `{side}` = `backend|frontend|be|fe`
- `{layer}` = `presentation|application|domain|integration|controller|usecase|repository|assembly`
- `{name}` may contain dot segments if explicitly allowed by regex (decision pending)

Examples:
```
component:manage-profile:display-profile:ProfileView:frontend:presentation
component:resolve-dilemmas:emit-decision:decision.mapper:backend:application
```

### 6.2 Feature Composition (Above Layers)
```
component:{wagon}:{feature}:composition:{side}:assembly
```
Example:
```
component:navigate-domains:browse-hierarchy:composition:backend:assembly
```

### 6.3 Wagon Entrypoints (Above Features)
```
component:{wagon}:wagon:{name}:{side}:assembly
```
Example:
```
component:navigate-domains:wagon:entrypoint:backend:assembly
```

### 6.4 Train Infrastructure Components
Treat `trains` as a reserved wagon slug for train infra.

```
component:trains:{feature}:{name}:{side}:assembly
```
Examples:
```
component:trains:runner:TrainRunner:backend:assembly
component:trains:model:TrainSpec:backend:assembly
component:trains:model:TrainStep:backend:assembly
component:trains:model:TrainResult:backend:assembly
component:trains:model:Cargo:backend:assembly
component:trains:model:WagonResult:backend:assembly
```
Rule: train infrastructure components are `assembly` layer only.

## 7. Train Orchestrators (Theme Files)
Theme orchestrator files in `python/shared/{theme}.py` use:

```
# URN: train:{train_id}
```

Theme is derived from train plan metadata (`themes` field in `plan/_trains/{train_id}.yaml`; use the first theme if multiple are listed).

## 8. Resolver Mapping (Component)
### 8.1 Standard Mapping (Existing)
Component resolution remains as today: map wagon/feature + side/layer into the standard directory search paths.

### 8.2 Train Infrastructure Mapping
For `component:trains:*` only, resolve in:
1. `python/trains/{feature}/`
2. `python/trains/`

No `assembly/` directory is required.

### 8.3 Matching Rule (Deterministic)
Matching must be deterministic to avoid substring collisions.

Decision pending: exact rule (proposed = case-insensitive stem match, not substring).

### 8.4 Test URN Resolution
Test URNs resolve by header scanning only (the `# URN: test:...` line). No path-based derivation is required beyond header detection.

## 9. Explicit Test URNs (Required)
There are two tiers of tests with distinct headers and URN formats.

### 9.1 Acceptance Tests (unit/component/integration)
Required header:
```
# URN: test:{wagon}:{feature}:{WMBT_ID}-{HARNESS}-{NNN}-{slug}
# Acceptance: acc:{wagon}:{WMBT_ID}-{HARNESS}-{NNN}[-{slug}]
# WMBT: wmbt:{wagon}:{WMBT_ID}
# Phase: RED|GREEN|REFACTOR
# Layer: presentation|application|domain|integration|assembly
```

Example:
```
# URN: test:authenticate-identity:verify-session:M002-UNIT-003-trace-spans-created
# Acceptance: acc:authenticate-identity:M002-UNIT-003
# WMBT: wmbt:authenticate-identity:M002
# Phase: RED
# Layer: application
```

### 9.2 Journey Tests (E2E)
Required header:
```
# URN: test:train:{train_id}:{HARNESS}-{NNN}-{slug}
# Train: train:{train_id}
# Phase: RED|GREEN|REFACTOR
# Layer: assembly
```

Example:
```
# URN: test:train:0025-onboarding:E2E-001-full-login-flow
# Train: train:0025-onboarding
# Phase: RED
# Layer: assembly
```

Canonical casing is `# URN:` (parsers may be case-insensitive).

### 9.3 Test URN Schemas
**Acceptance tests:**
```
test:{wagon}:{feature}:{WMBT_ID}-{HARNESS}-{NNN}-{slug}
```
- `{WMBT_ID}` = `[A-Z]\d{3}`
- `{HARNESS}` = allowed harness enum (UNIT, HTTP, EVENT, WS, E2E, A11Y, VIS, METRIC, JOB, DB, SEC, LOAD, SCRIPT, WIDGET, GOLDEN, BLOC, INTEGRATION, RLS, EDGE, REALTIME, STORAGE)
- `{NNN}` = 3 digits
- `{slug}` = kebab-case description (required)
Parsing rule: treat the first three dash-separated segments as `{WMBT_ID}-{HARNESS}-{NNN}`. Any remaining suffix is `{slug}`.

**Journey tests (E2E):**
```
test:train:{train_id}:{HARNESS}-{NNN}-{slug}
```
- `{train_id}` = `NNNN-kebab-case`
- `{HARNESS}` should be `E2E` for journey tests.
- `{NNN}` = 3 digits
- `{slug}` = kebab-case description (required)

### 9.4 File-Level Rule
Every test file must include exactly one `test:` URN (file-level identity even if multiple test cases exist).

Acceptance tests must include exactly one `Acceptance:` and one `WMBT:` line and must omit `Train:`.  
Journey tests must include `Train:` and must omit `Acceptance:` and `WMBT:`.

### 9.5 Component Test Link (Required)
Components must declare which tests validate them.

Header format in component files:
```
# URN: component:{wagon}:{feature}:{name}:{side}:{layer}
# Tested-By:
# - test:{wagon}:{feature}:{WMBT_ID}-{HARNESS}-{NNN}-{slug}
# - test:train:{train_id}:{HARNESS}-{NNN}-{slug}
```

Notes:
- `Tested-By` is required for all production components.
- During migration, `Tested-By` may be auto-filled only if discovery is unambiguous.
- For ambiguous candidates, the tool must list choices and require manual selection.
- For `component:trains:*`, `Tested-By` is manual only by default (no auto-discovery from journey E2E tests).
- `Tested-By` is authoritative for component→test edges; derived mappings are advisory only.
- Validator must ensure `Tested-By` tests align with the current acc→wmbt→feature chain (acceptance tests) or train plan (journey tests) to prevent drift.

## 10. Validation Rules
1. Every production code file must include a `component:` URN.
2. Every test file must include a `test:` URN.
3. Acceptance tests must include exactly one `Acceptance:` line and one `WMBT:` line; journey tests must include `Train:` and must omit `Acceptance:` and `WMBT:`.
4. `Acceptance:` line (if present) must reference a valid `acc:` URN.
5. `WMBT:` line (if present) must reference a valid `wmbt:` URN.
6. `component:trains:*` is valid and reserved.
7. `assembly` is a valid layer for component URNs.
8. Every production component must include `Tested-By` with valid `test:` URNs.
9. Feature slug `wagon` is reserved for wagon entrypoints; it may not be used as a real feature slug.
10. Wagon slugs `train` and `trains` are reserved; they may not be used in `wagon:` URNs.
11. Train sequences must be linear (steps only; no loops/routes/branching).
12. Test header `Phase:` must be one of `RED|GREEN|REFACTOR`.
13. Test header `Layer:` must be one of the allowed layer values.
14. Journey tests must use the `test:train:{train_id}:...` URN format; acceptance tests must use the `{wagon}:{feature}:{WMBT_ID}-{HARNESS}-{NNN}-{slug}` format.

Production code scope (for Rule 1):
- Include: `python/`, `web/`, `supabase/functions/` source files.
- Exclude: tests, migrations (`supabase/migrations/`), generated files, config-only modules, and scripts.
- `__init__.py` is excluded only if empty or import-only; if it contains logic, it must have a `component:` URN.

## 11. Toolkit Changes Required (ATDD)
**Conventions**
- `src/atdd/coder/conventions/green.convention.yaml`: update component URN marker format, add `assembly` layer, add feature composition + wagon entrypoint examples, add train infra examples.
- `src/atdd/planner/conventions/component.convention.yaml`: update component URN pattern/regex and examples to colon format with `{side}:{layer}` and `assembly`.
- `src/atdd/planner/conventions/train.convention.yaml`: set train URN to `train:{train_id}` and add explicit rule: trains are linear only (no loops/routes/branching). New journeys require new trains.
- `src/atdd/tester/conventions/red.convention.yaml`: update test header template to include `test:` URN + `Acceptance` + `WMBT` + `Phase` + `Layer`.
- `src/atdd/tester/conventions/filename.convention.yaml`: document that test identity comes from `test:` URN, while filename still derives from acceptance URN.
- `src/atdd/tester/conventions/train.convention.yaml` (or tester equivalent): require `Train:` header for E2E journey tests.

**Schemas**
- `src/atdd/planner/schemas/component.schema.json`: update URN regex to colon format and allow `assembly` layer.
- `src/atdd/planner/schemas/feature.schema.json`: ensure component references align with updated component URN format.
- `src/atdd/planner/schemas/train.schema.json`: enforce linear sequences by removing `loop` and `route` from `sequence` items.
- `src/atdd/tester/schemas/test_filename.schema.json`: clarify source of acceptance URN when `test:` header is primary.

**Utils (URN + Resolver)**
- `src/atdd/coach/utils/graph/urn.py`: update `train` pattern to `train:{train_id}`; update `component` pattern to allow `assembly` layer and any agreed name rules (dot segments if approved); update `test` pattern to allow both acceptance and journey forms.
- `src/atdd/coach/utils/graph/resolver.py`:
  - `ComponentResolver`: add reserved wagon slug `trains` mapping to `python/trains/{feature}/` then `python/trains/`.
  - `TestResolver`: parse `# URN: test:...` headers; only auto-generate if explicit `test:` is missing (if migration mode is allowed).

**Validators**
- `src/atdd/tester/validators/test_dual_ac_reference.py`: replace “header must be `acc:`” with new header format; use `Acceptance:` line for AC URN.
- `src/atdd/tester/validators/test_typescript_test_structure.py`: accept new header format (test URN + Acceptance line).
- `src/atdd/tester/validators/test_typescript_test_naming.py` and `src/atdd/tester/validators/test_acceptance_urn_filename_mapping.py`: extract acceptance URN from `Acceptance:` header line instead of `# URN: acc:...`.
- Add new validator: enforce exactly one `test:` URN per test file and validate acceptance vs journey URN formats.
- Add new validator: enforce `Tested-By` header in components and verify referenced tests exist.
- Add new validator: E2E journey tests must include `Train:` header with valid train URN.
- Update `src/atdd/planner/validators/test_train_validation.py`: fail immediately if any `loop` or `route` is present; enforce sequential step numbering with no gaps.
- Add new validator: forbid feature slug `wagon` and wagon slugs `train`/`trains`.
- Extend test header validator to require `Phase:` and `Layer:` values in the allowed enums and exactly one `Acceptance:` line.

**Commands / Generators**
- Update test templates in `src/atdd/tester/schemas/*.tmpl.json` to emit the new header block with `test:` + `Acceptance` + `WMBT` + `Phase` + `Layer`.
- Add fixer command to insert/repair test headers across all languages (Phase/Layer auto-inserted if missing).
- Add fixer command to insert `Tested-By` in components using unambiguous discovery (Option A).
- Add audit command to report non-linear trains (loops/routes) with file paths and offending nodes (no mutations).
- Add audit command to detect legacy `test:` URN formats before strict enforcement.

**Documentation**
- Update README and any ATDD docs that show URN header examples to match the new test header format and `assembly` layer.

## 12. Compatibility / Migration
- Existing `component:` URNs remain valid unless missing or malformed.
- Explicit `test:` URNs are required for new tests. Run an audit to detect any legacy `test:` formats before enabling strict validation.
- Train URNs must be `train:{train_id}`; update any theme-encoded train URNs in headers and tooling.
- During migration, auto-generated test URNs may be allowed only when explicit URNs are missing (opt-in migration mode).
- `Tested-By` may be auto-filled only when discovery is unambiguous; otherwise manual curation is required.
- `component:trains:*` remains manual linking unless train-specific tests explicitly declare a `Train:` header and you opt into mapping.
- Provide a linearity audit report listing all trains that still use loops/routes to guide remediation.

## 13. Risks
- Reserved wagon slugs `train`/`trains` must remain unused for actual wagons.
- Resolver matching must be deterministic to avoid collisions.
- Legacy test URN formats (if any exist in code) must be migrated before strict validation.

## 14. Open Questions
1. Do we allow dot-segments in `{name}` for `component:` URNs (requires regex change)?
2. What exact resolver matching rule should be enforced (exact stem match vs other)?
3. Should train orchestrator files also carry `component:` URNs, or remain `train:` only?

## 15. Implementation Checklist

Tasks are ordered by dependency. Blocked tasks cannot start until their prerequisites are complete.

### Phase 1: Foundation
| # | Task | File(s) | Spec Ref | Status |
|---|------|---------|----------|--------|
| 1 | Update URN patterns: `train` to `^\d{4}-[a-z0-9-]+$`, `component` to allow `assembly`, `test` to support acceptance + journey formats | `urn.py` | S5, S6, S9.3 | [ ] |

### Phase 2: Core Resolvers (blocked by Phase 1)
| # | Task | File(s) | Spec Ref | Status |
|---|------|---------|----------|--------|
| 2 | ComponentResolver: add `trains` wagon slug mapping to `python/trains/`, switch to case-insensitive stem match | `resolver.py` | S8.2, S8.3 | [ ] |
| 3 | TestResolver: parse explicit `# URN: test:...` headers (acceptance + journey), parse `Acceptance:`, `WMBT:`, `Train:`, `Phase:`, `Layer:` metadata lines | `resolver.py` | S8.4, S9.1, S9.2 | [ ] |

### Phase 3: Graph Builder (blocked by Phase 2)
| # | Task | File(s) | Spec Ref | Status |
|---|------|---------|----------|--------|
| 4 | Parse `# Tested-By:` from component files for authoritative component→test TESTED_BY edges; parse `# Train:` from journey tests for train→test edges | `graph_builder.py` | S9.5 | [ ] |

### Phase 4: Conventions (independent)
| # | Task | File(s) | Spec Ref | Status |
|---|------|---------|----------|--------|
| 5 | Add `assembly` layer, feature composition, wagon entrypoint, train infra examples | `green.convention.yaml` | S6, S11 | [ ] |
| 6 | Update component URN pattern/regex to colon format with `assembly` | `component.convention.yaml` | S6, S11 | [ ] |
| 7 | Set train URN to `train:{train_id}`, add linear-only rule | `train.convention.yaml` (planner) | S7, S11 | [ ] |
| 8 | Update test header template for two-tier format (acceptance + journey) | `red.convention.yaml` | S9.1, S9.2, S11 | [ ] |
| 9 | Document test identity from `test:` URN, filename from acceptance URN | `filename.convention.yaml` | S9.4, S11 | [ ] |
| 10 | Require `Train:` header for E2E journey tests | `train.convention.yaml` (tester) | S9.2, S11 | [ ] |

### Phase 5: Schemas (independent)
| # | Task | File(s) | Spec Ref | Status |
|---|------|---------|----------|--------|
| 11 | Update URN regex to colon format, allow `assembly` layer | `component.schema.json` | S6, S11 | [ ] |
| 12 | Align component references with updated URN format | `feature.schema.json` | S6, S11 | [ ] |
| 13 | Remove `loop`/`route` from sequence items, enforce linear-only | `train.schema.json` | S10 R11, S11 | [ ] |
| 14 | Clarify acceptance URN source when `test:` header is primary | `test_filename.schema.json` | S9, S11 | [ ] |

### Phase 6: Validators
| # | Task | File(s) | Spec Ref | Blocked By | Status |
|---|------|---------|----------|------------|--------|
| 15 | Replace `acc:` header check with `Acceptance:` line format | `test_dual_ac_reference.py` | S9, S11 | — | [ ] |
| 16 | Accept new header format, extract acc URN from `Acceptance:` line | `test_typescript_test_structure.py`, `test_typescript_test_naming.py`, `test_acceptance_urn_filename_mapping.py` | S9, S11 | — | [ ] |
| 17 | Enforce one `test:` URN per file, validate acceptance + journey formats, validate mutual exclusion (Acceptance+WMBT vs Train) | new validator | S9.4, S10 R2,3,14 | Phase 1 | [ ] |
| 18 | Enforce `Tested-By` header in components, verify referenced tests exist, validate chain alignment | new validator | S9.5, S10 R8 | Phase 3 | [ ] |
| 19 | E2E journey tests must include `Train:` header with valid train URN | new validator | S9.2, S10 R3 | — | [ ] |
| 20 | Fail on `loop`/`route` in train sequences, enforce sequential step numbering | `test_train_validation.py` | S10 R11 | — | [ ] |
| 21 | Forbid feature slug `wagon`, wagon slugs `train`/`trains` | new validator | S10 R9,10 | — | [ ] |
| 22 | Validate `Phase:` in `RED|GREEN|REFACTOR`, `Layer:` in allowed values | new/extended validator | S10 R12,13 | — | [ ] |

### Phase 7: Commands / Generators
| # | Task | File(s) | Spec Ref | Blocked By | Status |
|---|------|---------|----------|------------|--------|
| 23 | Emit new header block (test: + Acceptance + WMBT + Phase + Layer) for both tiers | `*.tmpl.json` | S9, S11 | — | [ ] |
| 24 | Insert/repair test headers across all languages (Phase/Layer auto-inserted if missing) | new fixer command | S11 | #17 | [ ] |
| 25 | Insert `Tested-By` in components using unambiguous discovery; list choices for ambiguous | new fixer command | S9.5, S11 | #18 | [ ] |
| 26 | Report non-linear trains (loops/routes) with file paths and offending nodes (no mutations) | new audit command | S11 | — | [ ] |
| 27 | Detect legacy dot-format `test:` URNs before strict enforcement | new audit command | S11, S12 | — | [ ] |

### Phase 8: Documentation
| # | Task | File(s) | Spec Ref | Status |
|---|------|---------|----------|--------|
| 28 | Update README + ATDD docs: new test header examples, assembly layer, train URN format, Tested-By | README, docs | S11 | [ ] |

### Implementation-to-Spec Conformance Checklist

Before marking any task complete, verify the implementation matches the spec:

| Check | Spec Reference | What to Verify |
|-------|---------------|----------------|
| Train URN has no theme | S5, S7 | `train:{train_id}` only; theme is in plan YAML `themes` field, not in URN |
| Train ID format | S5 | Pattern `^\d{4}-[a-z0-9-]+$` enforced in urn.py and validators |
| Assembly layer valid | S6, S10 R7 | `assembly` accepted in component URN pattern and schema regex |
| Train infra assembly-only | S6.4 | `component:trains:*` rejects non-assembly layers |
| Reserved slugs enforced | S10 R9,10 | Wagon slugs `train`/`trains` and feature slug `wagon` rejected by validator |
| Two-tier test headers | S9.1, S9.2 | Acceptance tests: `Acceptance:` + `WMBT:`, no `Train:`; Journey tests: `Train:`, no `Acceptance:`/`WMBT:` |
| Test URN formats | S9.3 | Acceptance: `test:{wagon}:{feature}:{WMBT_ID}-{HARNESS}-{NNN}-{slug}`; Journey: `test:train:{train_id}:{HARNESS}-{NNN}-{slug}` |
| One test URN per file | S9.4 | Exactly one `# URN: test:...` per test file |
| Tested-By authoritative | S9.5 | Component→test edges built from `Tested-By` headers, not from test file scanning |
| Phase/Layer validated | S10 R12,13 | Phase in `RED\|GREEN\|REFACTOR`; Layer in allowed enum |
| Deterministic resolver | S8.3 | Component matching uses case-insensitive stem match, not substring |
| Test resolver is header-only | S8.4 | No path-based derivation; `# URN: test:...` header scanning only |
| Linear trains enforced | S10 R11 | No `loop`/`route` in sequences; sequential step numbering |
| Graph edges correct | S9.5 | `acc→test` TESTED_BY from test scanning; `component→test` TESTED_BY from Tested-By headers; `feature→component` CONTAINS |
