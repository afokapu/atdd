# ATDD Extension-Detector ↔ Legacy-Validator Parity Audit (READ-ONLY)

**Repo:** `/Users/alecfokapu/Github/atdd/issue-1238-plan` (branch `feat/extension-enforcement-runner`)
**Bound set:** 26 conventions in `.atdd/binding.lock.yaml`, all `disposition: bound`, workspace `atdd.workspace.python-pytest` v0.1.0.
**Oracle:** legacy in-core validators under `src/atdd/{coder,tester}/validators/`.
**Run recipe (verified):** `ATDD_SCAN_ROOTS='["<ABSOLUTE path>"]' ATDD_IMPL_ID=<rule_id> python3 <ws>/cli/scan.py` → v1.1 JSON violations on stdout. NB: relative scan roots resolve against the impl dir and silently scan nothing — absolute paths are mandatory (an early aggregate run with relative `src/atdd` produced false all-zeros).
**Method:** per rule, read legacy + extension + report test; extract scope/roots/thresholds/exemptions; run extension over its own `fixtures/{dirty,clean}` (all 26 fire correctly) and over `src/atdd` (absolute); diff bound-rule-scoped; classify. Detail per batch verified by 6 parallel sub-audits + lead cross-checks on the anchors.

---

## Counts (of 26)

| Class | Count | Rules |
|---|---|---|
| **PARITY** | 17 | dead-code-ts, dup-py, dup-ts, complexity-cyclo, quality-mi, quality-mi-ts, logging.structured, silent-swallow*, nplus1*, boundaries.http-client, boundaries.xlang-entity, error-response.bare-string, design.primitives, gsap-layer, i18n-config, no-collaborator-substitution, no-polluting-patterns |
| **REGRESSION** | 5 | dead-code.reachability, logging.print, refactor.composition-consumer, security.sql-injection, metric-implementation-must-exist |
| **IMPROVEMENT** | 1 | complexity-cyclomatic-typescript |
| **NET-NEW (correct)** | 1 | tester.filename.urn |
| **UNVERIFIED** | 2 | refactor.coach-ratchet-pres, live-smoke-acceptance-must-execute |

\* conditional PARITY — see notes (relocated hardcoded carve depends on the caller re-supplying it).

---

## Cross-cutting finding 0 — THE SYSTEMIC PATTERN: legacy scope/root/exclusion knowledge relocated to the caller, not yet re-supplied

The hermetic decoupling consistently moved legacy's **hardcoded scope, graph roots, and exclusion carves OUT of the detector** onto caller-supplied `ATDD_SCAN_ROOTS` / `ATDD_SCAN_EXCLUDES`. Correct in principle (decoupling), but where the caller (enforce runner / `compute_scan_policy` / `.atdd/config.yaml`) does NOT re-express that knowledge, the extension **over-scans (false positives)** or **under-roots (false negatives)** relative to legacy. The operator-flagged dead-code regression (dropped `[project.scripts]` roots) is one instance of a pattern that recurs in **≥7 detectors**:

| Detector | Legacy knowledge dropped/relocated | Result if caller doesn't resupply |
|---|---|---|
| dead-code.reachability | pyproject `[project.scripts]` entry-point **roots** | FP: entry-only-reachable modules flagged dead |
| metric-implementation | installed-toolkit `src/atdd/runners/metrics` fallback **root** | FN: toolkit-provided metrics seen as missing |
| security.sql-injection | convention **excludes** `**/tests/**`,`**/migrations/**`,`**/conftest.py` | FP: dynamic SQL in tests/migrations |
| duplication-py | convention **excludes** `**/validators/**`,`**/templates/**`,`**/migrations/**` | FP: dup inside validators/templates |
| silent-swallow | `/fixtures/` **carve** | FP: silent-swallow inside fixtures |
| nplus1 | `/migrations/` **carve** | FP: DB-in-loop in migration scripts |
| logging.print | excludes **entirely ignored** (report test never forwards them) | FP: print() in any tree a consumer excludes |
| composition-consumer | `src/atdd` dogfood root + `is_excluded_fixture` guard + whole TS/Supabase stacks | FN: missed cross-stack true positives |

**Fix shape (uniform):** bake each legacy carve/root as a per-rule DEFAULT (in the detector or in `compute_scan_policy`'s rule-level roots/excludes) so parity does not depend on every consumer hand-writing a `scan:` block.

---

## Cross-cutting finding 1 — E004 "dogfood parity" is hollow on THREE compounding layers (none is parity)

Acceptance `acc:enforce-binding-plan:E004-SMOKE-001` promises "the pass/fail diff [vs the legacy in-core validators] is empty for the bound set." The implementing test `src/atdd/enforce_binding_plan/run_binding_plan/tests/test_e004_smoke_001_dogfood_parity.py` does **not** diff legacy at all — it asserts `proc.returncode == 0` (line 40) and `"coder.logging.print" not in output` (line 46). It passes for three reasons, none of which establishes parity:

1. **Vacuous oracle.** Legacy coder validators are hardcoded to consumer-layout dirs — `REPO_ROOT/web` (24 refs), `python` (23), `supabase`, `typescript`, `frontend`, `lib`, `contracts`, `dart`. **None exist in the toolkit repo; none scan `src/atdd`.** Over this checkout the legacy validators skip/return-empty. "src/atdd is clean under legacy" is true by vacuity, not verification. **Affects all 26 rules' src/atdd comparison.**
2. **Runner evaluates only 1/26 rules.** The in-core runner `src/atdd/enforce/runner.py` gates "runnable" on `_impl_has_report_channel()` (line 150), which checks for the literal file `test_logging_print_report.py` (`_PROVIDER_REPORT_TEST`, line 57). Only the print impl ships that filename → **25/26 rules return `unrunnable`** (not `fail`). This is a **desync**: the vendored `cli/scan.py` was generalized (reads each manifest's `report:` field, runs all 26 — verified), but the runner still hardcodes the print report-test filename and never reads `report:`.
3. **The 26th rule is exempted.** `coder.logging.print` is rule-exempt over `src/atdd` (`_TOOLKIT_CLI_EXEMPT_RELPATH`, `conventions.py:37`) → status `exempt`, not `fail`.

Net: the runner names **zero** bound rules as failing over src/atdd because 25 are unrunnable + 1 is exempt — and legacy is never invoked. **Evidence of the hollowness:** raw `cli/scan.py` over `src/atdd` (absolute paths) produces hundreds of findings the E004 test never surfaces — dead-code **276**, silent-swallow **299**, logging.print **1578**, complexity **680** (cyclo 187), composition-consumer **66**, quality-mi **105**, structured **15**. (Most are not "bugs in src/atdd" — they reflect scope/anchor differences — but they prove E004's exit-0 is not a parity signal.)

**Fixes:** (a) make E004 actually run the legacy validators over the SAME files and diff verdict sets (or, since legacy can't see src/atdd, diff over each detector's fixtures); (b) update `runner._impl_has_report_channel` to read the manifest `report:` field (mirroring `cli/scan.py._report_test_name`) so all 26 are runnable; (c) re-express the legacy scope carves in `compute_scan_policy` so the dogfood scope is comparable.

---

## Cross-cutting finding 2 — enforcement NARROWING at the binding layer (separate from per-rule parity)

Several legacy validator files bind MANY rule_ids; the bound set in `binding.lock.yaml` binds only ONE per detector, even though the detector EMITS all siblings. The detector does not narrow; the **binding** does. Sibling rule_ids are emitted-but-unbound → the disposition gate ignores them → those legacy enforcements are silently dropped:

- `test_complexity.py`: legacy binds cyclomatic + **nesting/length/params/cognitive** (10/4/50/6/15). Only `complexity-cyclomatic` bound. (Detector emits all 5 — over src/atdd: nesting 216, length 104, cognitive 173 — all unbound.)
- `test_complexity_typescript.py`: only `complexity-cyclomatic-typescript` bound; nesting-ts/length-ts unbound.
- `test_quality_metrics.py`: only `quality-mi` bound; **comments/duplication/naming/file-length unbound** (and ironically these are the only ones that fire on the fixture; quality-mi itself does not).
- `test_quality_metrics_typescript.py`: only `quality-mi-typescript` bound; comments-ts unbound.
- `test_security_patterns.py` (sql-injection bound; missing-auth/hardcoded-secret EMITTED + would be enforceable but only sql is in lock — though detector emits all 3).
- `test_design_system_compliance.py` (7 rule_ids), `test_gsap_layer_usage.py` (2), `test_i18n_runtime.py` (2), `test_cross_language_consistency.py` (4), `test_error_response_compliance.py` (2), `test_composition_completeness.py` (2): for these the detector emits ALL siblings, but only ONE per detector is in the lock. Whether the others are gated depends on whether the runner enforces every emitted rule_id or only bound ones — by the lock, only the bound one.

This is not a per-rule parity defect but a **coverage reduction** the migration introduces; flag for #1207 before retiring the multi-rule legacy validators.

---

## Cross-cutting finding 3 — dropped-root/entry-point awareness recurs beyond dead-code: YES

Confirmed (see finding 0 table). The dead-code "dropped roots" shape is the most visible case of a SYSTEMIC relocation of scope/root/exclusion knowledge. Two are genuine dropped-ROOT analogues (dead-code: entry-point roots; metric-implementation: installed-toolkit metrics root); the rest are dropped/relocated EXCLUSION carves with the same FP consequence.

---

## Per-rule table (all 26)

| # | rule_id | legacy validator | classification | root cause / note | recommended fix |
|---|---------|------------------|----------------|-------------------|-----------------|
| 1 | coder.dead-code.reachability | test_dead_code_python.py | **REGRESSION** (latent) | Dropped pyproject `[project.scripts]` CLI-entry-point roots (`find_cli_entry_points`, "NOT PORTED" docstring L28-31). Proven on isolated `/tmp/dctest`: entry-only `cli.py`+`handler.py` flagged dead by ext, root by legacy. | Port entry-point roots: have the enforce layer parse pyproject and inject those module files into the root set (scan-policy input), keeping detector hermetic. |
| 2 | coder.dead-code.reachability-typescript | test_dead_code_typescript.py | PARITY | 1:1 port; main/app entry roots present (no pyproject analogue in TS). 29 hits over src/atdd are all TS test fixtures (scope-selection artifact). | none (detector); scope-select is consumer policy. |
| 3 | coder.duplication.no-intra-layer-code-python | test_duplication_detector.py | PARITY (cond.) | Threshold (5 stmts, exact-hash), layers, #960 header-strip all match. Legacy `**/validators/**`,`**/templates/**`,`**/migrations/**` excludes relocated to caller. | Bake those 3 globs as detector/policy default excludes. |
| 4 | coder.duplication.no-intra-layer-code-typescript | test_duplication_detector_typescript.py | PARITY | Threshold (7 lines) + normalization byte-identical. NOTE: convention is `documentation-only`/warning but impl labels `strict` — if consumer enforces strict-FAIL, ext is STRICTER than oracle. | Reconcile disposition (warn vs strict) for the rule_id. |
| 5 | coder.refactor.complexity-cyclomatic | test_complexity.py | PARITY | `calculate_cyclomatic_complexity` byte-identical; threshold 10, <3-line guard match. Metric walk, no roots to drop. | none. (See narrowing: nesting/length/params/cognitive unbound.) |
| 6 | coder.refactor.complexity-cyclomatic-typescript | test_complexity_typescript.py | **IMPROVEMENT** | Ext repairs a legacy off-by-one (`_find_opening_brace(match.end()-1)`) that truncates EVERY TS function body → legacy flags 0 (structurally inert). Ext correctly measures (classify=15). True-positive recovery. | none for ext. File a separate tracker: legacy TS complexity/nesting/length validators are inert. |
| 7 | coder.refactor.quality-mi | test_quality_metrics.py | PARITY | `radon.mi_visit(...,multi=True)` + threshold 20 byte-identical; radon-absent→100.0 fallback identical. MI leg radon-gated AND fixture too weak to breach 20 → under-exercised but faithful. | Add a genuinely-low-MI fixture; ship radon as a provider dep so MI isn't silently inert. |
| 8 | coder.refactor.quality-mi-typescript | test_quality_metrics_typescript.py | PARITY | Pure-stdlib SEI MI formula + constants + threshold 20 byte-identical; fires on lowMi.ts (MI 14.2). Strongest positive demo of the 4. | none. |
| 9 | coder.logging.print | test_structured_logging.py (L36) | **REGRESSION** (latent) | Report test `test_logging_print_report.py` calls `scan_path(root)` WITHOUT excludes → `ATDD_SCAN_EXCLUDES` silently ignored (structured sibling proves the rest honor excludes). FP in any tree a consumer excludes to reconstruct legacy's `python/`-only / `src/atdd`-exempt scope. | One-line: forward `_exclude_globs()` to `scan_path` in the report test. (Or realize the rule via the structured detector, which honors excludes.) |
| 10 | coder.logging.structured | test_structured_logging.py (L37) | PARITY | LOG_METHODS/receiver set verbatim; detect-vs-disposition split matches legacy (emits raw incl. suppress-marked; consumer applies suppress-and-clean); excludes honored. | none. |
| 11 | coder.logging.coach-silent-swallow | test_no_silent_exception_swallowing_python.py | PARITY (cond.) | All handler-judging AST helpers + `self.logger` receiver match. Legacy `/fixtures/` carve relocated to caller `ATDD_SCAN_EXCLUDES`. | Resolver must supply `*/fixtures/*` exclude to reproduce legacy carve. |
| 12 | coder.refactor.nplus1 | test_query_count.py | PARITY (cond.) | DB/HTTP-in-loop AST + `# noqa: N+1` detection exemption verbatim. Legacy `/migrations/` carve relocated to caller. | Resolver must supply `*/migrations/*` exclude. |
| 13 | coder.refactor.composition-consumer | test_composition_completeness.py | **REGRESSION** (scope) | Ext realizes ONLY the Python leg; legacy enforces the SAME rule_id across python + typescript + supabase. Polyglot consumers MISS legacy TS/Supabase true positives. Also dropped `is_excluded_fixture` self-trigger guard. | Ship + bind the TS/Supabase composition detectors for the same rule_id; resolver supplies fixture-tree excludes. |
| 14 | coder.refactor.coach-ratchet-pres | test_presentation_ratchet_requires_smoke.py | **UNVERIFIED** | Pure reduction predicate (globs, >20%) byte-identical & fires on fixtures. BUT legacy verdict = git-diff (`collect_repo_reductions` vs origin/main) + smoke-evidence gate (`has_smoke_evidence`/`.atdd/smoke-evidence/<N>.yaml`); both externalized out of the hermetic detector to an unbuilt resolver+consumer. End-to-end verdict not exercisable; detector always emits even when legacy would pass via recorded evidence. | Build the git-diff resolver (writes `reductions.json`) + consumer-side smoke-evidence gate; then re-audit. |
| 15 | coder.boundaries.http-client | test_contract_driven_http.py | PARITY | `_RAW_FETCH_RE`, comment-skip, test-file-skip, skip-dirs byte-identical. Legacy `contract_driven_http.whitelist` (config) vs runner `scan.excludes`; both empty here. | Doc: re-express legacy whitelist as scan excludes; detector unchanged. |
| 16 | coder.boundaries.xlang-entity | test_cross_language_consistency.py | PARITY | Entity cross-lang logic faithfully ported (regex-over-text; discovers python/lib/contracts under each root — repo-structure-awareness replicable). Latent edges: src-layout python dir; `$id`-less `.schema` stem naming. | Mirror legacy `find_python_dir` src fallback; align `$id`-less entity naming. |
| 17 | coder.security.sql-injection | test_security_patterns.py | **REGRESSION** (latent) | AST sink/keyword detection verbatim, BUT legacy convention excludes (`**/tests/**`,`**/test_*.py`,`**/conftest.py`,`**/migrations/**`) dropped — not vendored, not sourced from convention; `_SKIP_DIRS` lacks tests/migrations. FP on dynamic SQL in test/migration files legacy suppresses. | Bake the security-convention SQL exclusions as default excludes for the rule (detector or `compute_scan_policy`). |
| 18 | coder.error-response.bare-string | test_error_response_compliance.py | PARITY | `BARE_STRING_DETAIL_RE` + HTTPException gate byte-identical; broader skip-dirs harmless. No legacy exclusion list existed → no dropped carve. | none. (Legacy artifact-integrity meta-tests have no home in ext path — note, not a rule_id loss.) |
| 19 | coder.design.primitives | test_design_system_compliance.py | PARITY | 12-entry `DESIGN_SYSTEM_IMPORTS` allowlist + presentation/ path filter + JSX regex byte-identical. Ratchet baseline = downstream (RAW parity holds). | none. |
| 20 | coder.presentation.gsap-layer | test_gsap_layer_usage.py | PARITY | 12 GSAP regex + `parts[2]=="presentation"` predicate identical. Ext routes commons→gsap-commons via elif (legacy double-emits); no site escapes (gsap-commons ported+strict) — cleaner labeling. | none (optional: emit both labels for exact per-site rule_id parity). |
| 21 | coder.presentation.i18n-config | test_i18n_runtime.py | PARITY | 5-path candidate list + hardcoded-array regex + manifest allowlist byte-identical. Legacy `locale_phase` gate NOT ported → moved to consumer mount-policy (mount only when localization in-scope). | Honor locale-phase at the policy layer (mount gate). |
| 22 | tester.acceptance-violation.live-smoke-acceptance-must-execute | test_live_smoke_execution.py | **UNVERIFIED** | Self-skip matcher at parity. BUT authority differs: legacy = plan/ `execution_kind` + URN→test join; ext = in-file `# execution_kind: live_smoke` header. Agree only if every anchored test carries the header (delegated to plan resolver). Latent MISS if header absent. Same-input comparison not constructible. | Have the runner pass the live_smoke test set from the plan resolver, or enforce the in-file header stamping; matcher unchanged. |
| 23 | tester.acceptance-violation.metric-implementation-must-exist | test_metric_implementation.py | **REGRESSION** | Swapped real-import `callable(compute)` over the registry for regex `^def compute`+`^def passes` over raw acceptance YAML. ADDS FPs (requires `passes` legacy doesn't; rejects non-`def`/lambda/imported compute) AND MISSES (can't see import failures; lost installed-toolkit `src/atdd/runners/metrics` fallback root). Authority population also shifts (registry rules → raw acceptances). | Drop `passes` requirement; resolve compute via import/AST-callable not `^def`; restore toolkit metrics fallback root; scan registry shape not raw YAML. |
| 24 | tester.filename.urn | (no rule-binding legacy enforcer) | **NET-NEW** (correct) | No legacy validator binds this rule_id (`test_acceptance_urn_filename_mapping.py` always `assert True`; `test_python_test_naming.py` enforces a different slug/dir property, binds no rule); rule is `documentation-only`/sev-2. Ext is a sound fresh realization: flags intended-but-non-collectable test files (URN header or top-level `def test_` under a non-`test_` name). Fires on fixtures; clean on well-named. | none. (Optional: add legacy slug-mandatory check = extra scope, not a regression.) |
| 25 | tester.smoke.no-collaborator-substitution | test_smoke_no_collaborator_substitution.py | PARITY | Two AST patterns (monkeypatch.setattr w/ env-method allowlist; obj.attr=local callable) + SyntaxError synthetic finding byte-identical. `# Phase: SMOKE` gate matches. Emits raw incl. suppressed (consumer disposition). | none (ensure suppress-and-clean applied downstream). |
| 26 | tester.test-isolation.no-polluting-patterns | test_no_polluting_patterns.py | PARITY | Full AST engine (bare-init-bad-cwd; core-bare-unscoped) + `_TMP_PATH_NAMES`/`-C`/`--worktree`/tmp_path exemptions ported verbatim. | none. |

---

## REGRESSION list, ranked by severity (5)

1. **coder.refactor.composition-consumer** — *scope regression.* Ext ships only the Python leg; legacy enforces the same rule_id across python + typescript + supabase. Over any polyglot consumer it **silently misses real true positives** (no error, just absence — the most dangerous failure mode). Fix: ship+bind the TS/Supabase composition detectors for the rule_id.
2. **tester.acceptance-violation.metric-implementation-must-exist** — *bidirectional correctness error.* Regex `def compute`+`def passes` over raw YAML replaced legacy's real-import `callable(compute)` over the registry → both FPs (spurious `passes` requirement, rejects non-`def` compute) and FNs (blind to import failures, lost toolkit metrics root). Fix: import/AST-callable resolution, drop `passes`, restore toolkit fallback root.
3. **coder.dead-code.reachability** — *latent FP (operator anchor).* Dropped pyproject `[project.scripts]` entry-point roots; modules reachable only via a console-script are falsely flagged dead. Proven on `/tmp/dctest`. Fix: inject resolved entry-point module files as graph roots via scan policy.
4. **coder.security.sql-injection** — *latent FP.* Dropped convention excludes (`**/tests/**`,`**/migrations/**`,`**/conftest.py`); dynamic SQL in test/migration files (which legacy suppresses) is flagged. Fix: bake the convention SQL exclusions as default excludes for the rule.
5. **coder.logging.print** — *latent FP, trivial fix.* The print report test never forwards `ATDD_SCAN_EXCLUDES` → excludes ignored; FP in any tree a consumer excludes to mimic legacy's hardcoded scope. (Lowest impact: the in-core runner also can't run it over consumer code yet, and exempts it over src/atdd.) Fix: forward `_exclude_globs()` to `scan_path` (one line).

---

## UNVERIFIED (2) — why

- **coder.refactor.coach-ratchet-pres** — the detector's pure reduction predicate is byte-identical to legacy and fires correctly, but legacy's full verdict needs a git-diff (`collect_repo_reductions` vs origin/main) + a smoke-evidence gate (`.atdd/smoke-evidence/<N>.yaml`), both externalized to an unbuilt resolver/consumer. End-to-end diff vs legacy is not exercisable from the detector.
- **tester.acceptance-violation.live-smoke-acceptance-must-execute** — self-skip matching is at parity, but the live_smoke *authority* differs (legacy: plan `execution_kind`+URN-join; ext: in-file header). They agree only if every anchored test carries the header, a precondition delegated to the plan resolver and unconfirmable from the detector — no clean same-input comparison.

---

*Read-only audit. No detector, validator, convention, config, or test was modified; nothing committed.*
