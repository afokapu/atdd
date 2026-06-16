# Planner Convention → Node Parity Ledger

> Purpose: double-check that the **legacy convention YAML** (`src/atdd/planner/conventions/*.convention.yaml`)
> and the **convention-node corpus** (`…/conventions/nodes/*.convention.yaml`) **+ the relationship
> graph** (`src/atdd/coach/graph/relationships.yaml`) carry the *same content*. Where they do not,
> the discrepancy is flagged here and closed by re-atomisation. Schema reference: *ATDD Convention
> Graph System v1.1* §5 (node), §6 (relationships).

## Parity definition

A legacy convention has **parity** when every normative content unit in it is represented in the
graph system:

| Legacy content unit | Parity home |
| --- | --- |
| Rule statement / requirement | node `statement` |
| Definitions, grammars, allowed-value lists, regexes, code maps, patterns | node `terms[].text` + `terms[].values` |
| Worked examples (positive / anti-pattern) | node `examples` + `terms[].examples` |
| Exceptions, allow-lists, draft-exemptions, suppression hatches | a dedicated `term` (§5.4) |
| Cross-rule dependencies ("presupposes", "subsumes", "mirrors", "follows") | a relationship `edge` |
| Enforcement metadata (severity / disposition / validator / fix_hint) | **out of scope for nodes** (§5/§D003) — lives in gates + validator code |

## Summary

| Legacy convention | Lines | Nodes | Node parity | Notes |
| --- | ---: | ---: | --- | --- |
| theme | 155 | 5 | ✅ high | taxonomy + boundary + retired-digits + exceptions recovered |
| coverage | 104 | 4 | ✅ high | both directions + all three allow-lists + draft exemptions recovered |
| issue-body | 84 | 2 | ✅ high | placeholder string + tag semantics + suppression recovered |
| criteria | 153 | 1 | 🟡 partial | harness catalog names captured; full per-harness given/then templates not |
| wagon | 301 | 2 | 🟡 partial | URN + kebab/snake + features format recovered; `artifact_contracts`, `coherence_checks`, refinement taxonomy not |
| feature | 427 | 2 | 🟡 partial | shape + sizing + hard_limits + feedback-loop recovered; full `footprint_scoring` tables, `artifact_seeds`, grouping/estimation not |
| acceptance | 595 | 2 | 🟡 partial | harness-code map + G/W/T + cap recovered; full 22-harness prompts/typical_layers, signal/telemetry, boundary_kinds, hermetic not |
| wmbt | 312 | 2 | 🟡 partial | URN + step codes + smoke + suppression recovered; 6 dimensions, lens catalog, `splitting_rules` not |
| steps | 153 | 1 | 🟡 partial | 9-step taxonomy + per-step examples recovered; full key_terms / linguistic_patterns / architecture per step not |
| appendix | 199 | 1 | 🟡 partial | types + naming + storage recovered; `llm_guidelines` workflow not |
| artifact-naming | 864 | 1 | 🟡 partial | grammar + separators + anti-patterns + cardinality + sample examples recovered; full ~40-example set, pluralization guide, migration guide, logical/physical JSON-Schema bodies not |
| **component** | 675 | **0** | ❌ **none** | **zero nodes — total parity failure** |
| **interface** | 382 | **0** | ❌ **none** | **zero nodes — total parity failure** |
| **train** | 605 | **0** | ❌ **none** | **zero nodes — total parity failure** |

## Flagged discrepancies

### A. Zero-node conventions (highest priority) — ~1,662 legacy lines with no graph representation

The prior atomiser only read each file's structured `rules:` block; `component`, `interface`, and
`train` have **no `rules:` block**, so nothing was extracted. Their normative content — much of it
rule-shaped and referenced by real validators — is entirely absent from the graph.

- **component** (675L): `component_type_catalog` (~60 component types × file-suffix × complexity
  weight), `urn_naming` (`component:{wagon}:{feature}:{name}:{side}:{layer}` + `lint_regex`),
  `validation_rules` (5 enforceable: `component_count ≤8`, `business_focus`, `layer_consistency`,
  `io_alignment`, `method_limit ≤5`), `artifact_derivation`, `layer_assignment`, `component_limits`.
- **interface** (382L): `artifact_contracts` (logical/physical patterns, "leaf dirs must have
  `tests/`" referenced by `test_contract_directories_have_tests_subdirectory`), `artifact_urns`
  (`contract:{domain}:{resource}[.{category}]`, `orphan_detection`), `naming_patterns`
  (events past-tense / state nouns / collections plural), `api_mapping`.
- **train** (605L): `numbering` (4-digit `[Theme][Category][Variation]`, regex
  `^[0-9]{4}-[a-z][a-z0-9-]*$`), `linearity_rule` (no loops/routes, no step gaps), `acceptances`
  invariants + `forbidden_fields`, `registry` two-file rule (`SPEC-TRAIN-VAL-0003`), `dependencies`
  (no circular), `artifact_flow` (produced_before_consumed), a 6-item `validation_rules` list.

**Remediation:** atomise each into multiple flat nodes (≈1 node per rule-shaped unit), embedding the
full catalogs/tables in `terms[].values`. Estimated ~12–18 new nodes.

### B. Residual within-family gaps (the 🟡 rows)

The re-atomisation captured each rule's statement, grammars, allowed-value lists and representative
examples, but several legacy **reference catalogs** are large and only their *names/keys* were
captured, not the full prose. For **exact** content parity these full tables should be embedded in
the relevant `terms[].values` (which keeps term count low while holding 100% of the content):

- **acceptance**: full 22-harness `harness_types` (description + prompt + typical_layers each);
  `gherkin_structure` signal/telemetry sub-tree; `boundary_kinds` (10); `hermetic` fidelity-contract.
- **artifact-naming**: the complete worked-example set (~40), `pluralization_guide`,
  `migration_guide` (v1→v2), `logical_vs_physical_mapping` physical-form JSON-Schema bodies.
- **feature**: `footprint_scoring` component-type weight tables + calculation formula; `artifact_seeds`.
- **wmbt**: the 6 `dimensions` (keywords/rationale/examples) and the social/functional/emotional
  `lenses` catalog; full `splitting_rules`.
- **steps**: per-step `key_terms`, `linguistic_patterns`, `architecture` layer-sequence.
- **wagon**: `artifact_contracts`, `coherence_checks` (7 rules), refinement theme taxonomy.
- **criteria**: per-harness given/then example templates.
- **appendix**: `llm_guidelines` during-creation / during-disambiguation workflow.

**Remediation:** deepen the affected nodes by moving the full legacy tables into `terms[].values`;
where a catalog is itself rule-shaped (e.g. wagon `coherence_checks`), split it into its own node.

### C. Relationship-graph gaps

The legacy text encodes cross-rule dependencies that are not yet edges (the graph has 13):

- `planner.theme.must-be-canonical` **subsumes** `wmbt:govern-lifecycle:E001` (legacy says so explicitly).
- `planner.wmbt.must-have-smoke-acceptance` **mirrors** `tester.smoke.pres` (#293).
- `planner.theme.archetype-alignment` **exercises** `wmbt:govern-lifecycle:L001`.
- New `component` / `interface` / `train` nodes will need edges (e.g. component-urn **requires** a
  wagon/feature, train acceptance **requires** WMBT acceptance shape).

**Remediation:** add edges (whole-rule or `rule_id#term_id` refs) as the new nodes land.

## Out of scope (by design, not a discrepancy)

Per §5 / §D003 nodes deliberately exclude enforcement metadata — `severity`, `disposition`,
`validator` bindings, `aliases`, `introduced_in`, `fix_hint`, `suppression_deadline`. These remain in
the legacy `rules:` blocks and (eventually) in gates + validator source. They are recoverable from a
node via its `rule_id`. Their absence from nodes is **not** a parity gap.

## Decisions taken

- **Schema depth:** large legacy reference catalogs are split into their own dedicated nodes
  (one section → one node), with full tables embedded in `terms[].values`.
- **Enforcement metadata** (`validator`/`severity`/`disposition`/`aliases`/`fix_hint`/`suppression`)
  stays **out of nodes** (v1.1 D003/D010). Legacy YAML remains its source of truth; parity is made
  auditable by a `source` provenance block on every node instead of duplicating it.
- **Provenance:** every node carries `source: {legacy_path, legacy_sha, legacy_rule_id?,
  extraction_mode: high_fidelity}`, stamped centrally and schema-validated.

## Status — RESOLVED

All flagged discrepancies are closed. The graph now carries **97 convention-nodes** and an
**88-edge** relationship graph; every node is schema-valid, every filename equals its `rule_id`,
every node carries a resolvable `source.legacy_path` (extraction_mode `high_fidelity`), and every
edge endpoint resolves to a real node.

- [x] Schema extended to §5.1 (`examples`, term `values`, term `examples`) + optional `source` block.
- [x] 11 rules-bearing conventions re-atomised to high node parity.
- [x] **A** — `component` (11), `interface` (8), `train` (7) atomised into split nodes.
- [x] **B** — dense families expanded into full section-node sets:
  acceptance +11, artifact-naming +9, wmbt +10, feature +7, wagon +6, criteria +5
  (each large legacy catalog now its own node with the full table in `terms[].values`).
- [x] Provenance `source` block stamped on all 97 nodes; smoke test guards it.
- [x] **C** — relationship edges grown from 13 → 88 (intra-family + cross-convention).

Node count by family: theme 5, coverage 4, issue-body 2, criteria 6, wagon 8, feature 9,
acceptance 13, wmbt 12, steps 1, appendix 1, artifact-naming 10, component 11, interface 8, train 7.

### Remaining (optional, low priority)
- `steps`, `appendix` and `coverage` were enriched in place and not split further; if exhaustive
  section-splitting is wanted there too (e.g. an `appendix.types` catalog node), it is a small
  follow-up. Enforcement metadata remains in legacy YAML + (future) gates by design.
