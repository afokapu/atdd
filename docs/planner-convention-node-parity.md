# Planner Convention → Node Parity Ledger

> **STATUS: CLOSED (#1111), and the legacy side no longer exists (#1639).**
>
> This is a **historical record of a completed re-atomisation**, not a current-state report. The
> Summary table below is the *pre-#1111 snapshot* that motivated the work; the outcome is recorded
> under [Status — RESOLVED](#status--resolved). Read the two together or not at all.
>
> Two rows of that snapshot (`component`, `interface`) were left reading "zero nodes — total parity
> failure" long after #1111 closed them at 11 and 8 nodes. #1639 was filed off those stale rows and
> had to be re-scoped after audit. They are corrected in place below.
>
> As of #1639 the legacy `src/atdd/planner/conventions/*.convention.yaml` monoliths are **deleted**.
> The convention-node corpus under `…/conventions/nodes/` is the sole source of truth, so there is no
> longer a "legacy side" for this ledger to compare against. Nothing here should be read as
> describing a file that still exists.

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

> **Historical snapshot — pre-#1111.** Every 🟡/❌ row below was closed by the re-atomisation; see
> [Status — RESOLVED](#status--resolved) for the final node counts. Do not cite this table as
> current state.

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
| component | 675 | **11** | ✅ covered | was ❌ "zero nodes" pre-#1111; atomised into 11 split nodes (type-catalog, urn, count-limit, method-limit, layer-assignment, layer-consistency, io-alignment, business-focus, derivation, artifact-derivation, structure). Corrected in #1639 — this row was stale for the whole interval and is what #1639 was mis-filed from. |
| interface | 382 | **8** | ✅ covered | was ❌ "zero nodes" pre-#1111; atomised into 8 split nodes (contract-urn, api-mapping, naming-patterns, artifact-transformation, structure-rules, ownership-rules, orphan-detection, tests-subdirectory). Corrected in #1639. |
| train | 605 | 38 | ✅ covered | atomised independently on `main` (post-#1421, typed `train:<subject>:<slug>` grammar); this audit's `numbering` / `registry` / `dependencies` findings are superseded by main's nodes |

## Flagged discrepancies

### A. Zero-node conventions (highest priority) — ~1,662 legacy lines with no graph representation

> **CLOSED by #1111.** The inventory below is the *finding*, not the current state: `component`,
> `interface` and `train` were atomised into 11 / 8 / 7 split nodes and every item listed here now
> has a node home. #1639 re-verified this section-by-section against the corpus and found **no
> normative content left unatomised** in any of the three. Retained for provenance only.

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

## Node schema — 1.1.0 (`atdd:author:convention-node:1.1.0`)

Final node shape: `schema_version · rule_id · kind · status · name · statement ·
implementation{type,ref} · source{legacy_path,legacy_section,legacy_rule_id,legacy_sha,
extraction_mode} · content{summary,normative_text,operational_guidance,examples,counter_examples,
constraints,exceptions,fix_hint} · metadata{aliases,severity,disposition,introduced_in,
suppression_deadline} · parity{source_fragments_preserved,examples_preserved,
implementation_preserved,fix_hint_preserved,reviewed_at} · terms[]{text,values,examples}`.

Enforcement rides on the node via the generic `implementation` block: the 23 legacy-rule-anchored
nodes carry `type: validator` with the real `<module>::<test>` ref plus
`metadata.severity/disposition/aliases` and `content.fix_hint` pulled from the legacy `rules:`
blocks; section nodes carry `type: none`. Relationships stay in the separate graph (§6).

## Status — RESOLVED

All flagged discrepancies are closed. The graph now carries **106 convention-nodes** and a
**103-edge** relationship graph; every node is 1.1.0-valid, every filename equals its `rule_id`,
every node carries a resolvable `source.legacy_path` (extraction_mode `high_fidelity`) and a
`parity` block, and every edge endpoint resolves to a real node.

- [x] Schema extended to §5.1 (`examples`, term `values`, term `examples`) + optional `source` block.
- [x] 11 rules-bearing conventions re-atomised to high node parity.
- [x] **A** — `component` (11), `interface` (8), `train` (7) atomised into split nodes.
- [x] **B** — dense families expanded into full section-node sets:
  acceptance +11, artifact-naming +9, wmbt +10, feature +7, wagon +6, criteria +5
  (each large legacy catalog now its own node with the full table in `terms[].values`).
- [x] Provenance `source` block stamped on all 97 nodes; smoke test guards it.
- [x] **C** — relationship edges grown from 13 → 88 (intra-family + cross-convention).

Node count by family: theme 5, coverage 6, issue-body 2, criteria 6, wagon 8, feature 9,
acceptance 13, wmbt 12, steps 4, appendix 5, artifact-naming 10, component 11, interface 8, train 7.

All fourteen legacy conventions are fully atomised into split section-nodes, including `steps`
(+jtbd-taxonomy, linguistic-patterns, architecture-routing), `appendix` (+types, naming-pattern,
storage, llm-guidelines) and `coverage` (+traceability-graph, rollout). Enforcement metadata is now
carried on each node via `implementation` + `metadata` (no longer "out of nodes").

**Source-of-truth update (#1639).** The sentence this paragraph used to end with — "the legacy
`*.convention.yaml` files remain the source of truth" — is retired. #1639 measured those files as
carrying **0 live rules** (no `rules:` block, no top-level `rule_id`, no glob consumer keying on
anything they hold) and deleted all 17. The nodes are the source of truth. Each node's
`source.legacy_path` is now a **provenance record of a deleted file**, not a live pointer; it is
retained deliberately so the extraction can still be audited against git history.
