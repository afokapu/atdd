# Convention Family Variant-Parity Report (#1212)

All 13 convention families now execute on the **real composed graph** (the canonical
substrate; `variant → archetype.evaluate(real_graph, config) → EVALUATORS[template_id]`).
Each planner+coach variant is wired to execute and its legacy parity is **measured** (legacy
run as a black-box `subprocess pytest` on the identical faulted tree, or — for advisory
metrics whose pytest passes regardless of findings — the legacy *scan function* in-process via
a non-`test_*` `_parity` helper, so the E013 no-legacy-import guard stays satisfied).

**263 conventions tests pass.** Clean baselines are 0 except where an advisory metric
genuinely fires on the valid corpus (documented, not a false positive).

## Per-family verdict

| family | template(s) | variants | both | convention-only | other (honest) |
|---|---|---|---|---|---|
| coherence | resolved_fact_agreement | 4 | 3 | — | theme_archetype_alignment = function-level parity (file-injection differential structurally impossible) |
| coverage | source_has_required_target, reachability_no_orphan | 3 | 2 | 1 (legacy warn-only / non-enforcing) | — |
| sizing | cardinality_bounds | 2 | 2 | — | advisory: clean baseline ≠0 by design (real corpus findings) |
| presence | required_field_presence, conditional_requirement | 5 | 3 | 2 (1 legacy vacuous, 1 representation mismatch) | — |
| acyclicity | forbidden_cycle_absence | 1 | 1 | — | — |
| boundary | allowed_boundary_crossing | 1 | 1 | — | — |
| policy | forbidden_construct_absence | 4 | 4 | — | CLAUDE.md checks (e022/r003) excluded → separate document-subject issue |
| binding | declaration_to_implementation_binding, emitted_identity_roundtrip | 4 | 4 | — | — |
| resolution | direct/artifact/reference_chain_resolution | 5 | 3 | 1 (legacy vacuous) | 1 not-measurable (legacy hermetic) |
| schema | node_schema_conformance | 1 | 1 | — | — |
| grammar | identifier_grammar_conformance | 1 | 1 | — | live-smoke counterpart |
| uniqueness | scoped_identifier_uniqueness | (done earlier) | 5 classes | 1 (train-id: legacy vacuous) | wmbt-id structural; telemetry-urn dormant |

## How to read the non-`both` verdicts (honest classification — none faked)

- **convention-only** = the convention check is *stricter* than its legacy counterpart, and
  the legacy validator is **vacuous or non-enforcing** (warn-only / dead fixture). These are
  coverage **improvements**, not false positives — verified true positives on real faults.
- **function-level parity** (coherence/theme_archetype_alignment) = a same-file fault-injection
  differential is structurally impossible; parity was proven at the scan-function level on a
  faulted tree (divergence sets equal), explicitly NOT claimed as `both`.
- **not-measurable** (resolution, 1) = the legacy validator is hermetic (no real-graph
  counterpart to inject against); recorded, not faked.

## Decommission readiness

A legacy planner/coach validator is decommissionable once its convention variant proves
`both` (or is an adjudicated convention-only improvement) AND `test_shadow_parity` / the
family suite is green. The variants above that reached `both` or convention-only-improvement
are decommission candidates; the function-level and not-measurable cases need a sign-off call
on whether scan-function parity / hermetic-exemption is sufficient.

**Decommission remains BLOCKED pending operator sign-off** on (a) the convention-only cases as
accepted improvements, and (b) the function-level / not-measurable exemptions. No legacy
validator has been removed.
