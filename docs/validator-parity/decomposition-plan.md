# Convention Validator Architecture — Decomposition Plan (#1204–#1207)

Locked decomposition for the convention-graph validator family/template migration.
The four `atdd plan` sessions trace against this document.

## Placement (shared)

- **Train:** `0001-self-compliance-validate`
- **Wagon:** `validate-conventions` (NEW) — bounded context: graph-question validator
  family/template suite under `src/atdd/validators/conventions/`.
  - theme: `commons`
  - subject: `agent:tester`
- The four issues are **phased feature-clusters in one wagon**, sequenced by the
  issue dependency chain. WMBT numbering is a single per-wagon sequence.
- Each issue binds to its own **local** ATDD issue record (manifest slug; GitHub #
  syncs downstream) on its own branch + worktree, at the session `confirm` boundary.

## Dependency chain

`#1204 → #1205 → #1206 → #1207` (strict linear; legacy validators are deleted only
in #1207, and only after parity is proven).

---

## #1204 — introduce architecture (refactor; root, unblocked)

**Main-job:** When the validator model is persona-organized, establish a
convention-graph family/template catalogue (13 families / 22 templates), registry,
template contract, and conformance check in ATDD Core — running parallel to legacy,
deleting nothing.

**Features**
- `feature:validate-conventions:family-template-catalogue` — 13 family folders
  (`presence`…`binding`), each `README.md` + `archetype.py` + `fixtures.py`;
  `_support/*`; `registry.yaml`; `_support/template_contract.py`.
- `feature:validate-conventions:registry-archetype-conformance` — smoke test that
  `registry.yaml` ↔ archetype exports agree.

**WMBTs**
- `E001` registry lists exactly 13 families / 22 templates (no extras, no omissions).
- `E002` each `archetype.py` exposes its assigned template IDs (registry↔code roundtrip).
- `E003` `template_contract.py` defines all 8 mandatory fields.
- `E004` every family folder has the 3 required files (`README.md`, `archetype.py`, `fixtures.py`).
- `C001` legacy persona folders unmoved + `atdd validate` behavior unchanged (regression guard).

**SMOKE acceptance:** run the conformance smoke proving registry↔archetype agreement
on the real source tree.

---

## #1205 — parity audit/map (audit; depends #1204)

**Main-job:** When legacy validators are persona-scattered, produce a deterministic,
exhaustive map: every legacy validator → family/template/variant/target-path/status/
priority, with no file unaccounted and no invented family.

Primary deliverables are docs (`docs/validator-parity/convention-validator-parity-audit.md`
+ `docs/validator-parity/legacy-validator-map.yaml`); the testable surface is a
**meta-validator over the map**.

**Features**
- `feature:validate-conventions:legacy-parity-audit` — the two audit artifacts + the
  completeness meta-validator.

**WMBTs**
- `E005` every file under the 4 legacy roots appears in `entries` or `excluded` (coverage).
- `E006` every entry's family/template exists in the #1204 registry (no invented families).
- `E007` every entry has a status from the 7-value enum + priority ∈ {P0,P1,P2}.
- `C002` excluded files each carry an explicit reason.

---

## #1206 — implement variants (feat; depends #1204, #1205)

**Main-job:** When the catalogue and parity map exist, instantiate concrete
metadata-driven variants (P0 then P1) under `conventions/<family>/test_<variant>.py`,
runnable in parallel with legacy, importing no legacy validator as source of truth.

**Features** (P0 and P1 both planned now; P2 deferred)
- `feature:validate-conventions:p0-graph-integrity-variants` — composition / resolution
  / schema / grammar / uniqueness / binding / coverage-reachability.
- `feature:validate-conventions:p1-parity-variants` — coverage-source / sizing /
  coherence / acyclicity / boundary / policy.
- `feature:validate-conventions:variant-metadata-conformance` — suite asserting
  variant well-formedness.

**WMBTs**
- `E008` every variant references an existing registry family/template.
- `E009` every variant declares the 9 metadata fields + ≥1 `legacy_parity_source` (unless new-only).
- `E010` every P0 `direct/split/merged/superseded` entry has an impl or superseded-evidence.
- `E011` no target validator imports a legacy persona module.
- `E012` target + legacy run in parallel (no collision).

**SMOKE acceptance:** execute a real P0 variant against a known-bad fixture and assert
it fails with template-shaped `failure_evidence`.

---

## #1207 — decommission legacy (refactor; depends #1204–#1206)

**Main-job:** Only after parity is proven, decommission persona validators via phased
shadow → promote → replace → docs, with a CI gate that prevents new persona-folder
convention validators and any legacy file without a decommission outcome.

**Features**
- `feature:validate-conventions:shadow-and-promote` — `shadow-run-report.md` + make
  conventions authoritative.
- `feature:validate-conventions:legacy-decommission` — per-file outcome
  (remove/shim/keep/move) + `legacy-validator-decommission-report.md`.
- `feature:validate-conventions:anti-regression-gate` — new CI guard checks.

**WMBTs**
- `E013` CI rejects a new convention-graph validator placed under a persona folder.
- `E014` shadow report shows zero unresolved P0 gaps.
- `E015` decommission report is 1:1 with the audit (every legacy file has an outcome).
- `C003` conventions run as the authoritative path.
- `Y001` (safety) refuse to delete any legacy file whose status ∉
  {direct,merged,split,superseded} or whose target is absent.

---

## Cross-cutting notes

- Doc-deliverable issues (#1205, #1207) stay ATDD-legal via a meta-validator + SMOKE
  asserting the artifacts exist, are registry-consistent, and are complete.
- The parallel-with-legacy invariant (no deletes until #1207) is encoded as `C001` in
  #1204 and re-asserted through #1206.
- Session order: #1204 authors the wagon + WMBT registry; #1205–#1207 add features /
  WMBTs to the existing wagon.

## Canonical catalogue reference (from #1204 body)

13 families: presence, uniqueness, resolution, schema, grammar, composition, coverage,
sizing, coherence, acyclicity, boundary, policy, binding.

22 templates: presence/{required_field_presence, required_relationship_presence,
conditional_requirement}; uniqueness/{scoped_identifier_uniqueness,
duplicate_edge_absence}; resolution/{direct_reference_resolution,
artifact_reference_resolution, reference_chain_resolution}; schema/node_schema_conformance;
grammar/identifier_grammar_conformance; composition/{composed_graph_loads,
composition_merge_identity, post_composition_edge_legality}; coverage/{reachability_no_orphan,
source_has_required_target}; sizing/cardinality_bounds; coherence/resolved_fact_agreement;
acyclicity/forbidden_cycle_absence; boundary/allowed_boundary_crossing;
policy/forbidden_construct_absence; binding/{declaration_to_implementation_binding,
emitted_identity_roundtrip}.
