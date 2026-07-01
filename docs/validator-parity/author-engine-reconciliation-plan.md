# Author ↔ Convention-Graph Engine Reconciliation Plan (#1097 ↔ #1206/#1212)

The convention-graph validator family (#1204/#1206/#1212) and the `atdd author`
substrate (#1097) evolved in parallel and are **not integrated**. This plan tracks
closing that gap. Discovered 2026-06-25 during the #1212 decommission sign-off review.

## The gap (measured)

- `atdd author` writes **single-node** convention files (`<role>/conventions/nodes/
  <rule_id>.convention.yaml`): top-level `rule_id`/`kind`/`status` + `implementation:
  {type, ref}`.
- The convention-graph engine (`_support/graph_loader.py`) discovers rules only from
  **`rules:[]` blocks** (`rules[].validator`).
- Result: **only 42 of 158** authored single-node files are visible to the engine; the
  graph sees **152** rule nodes but **116 authored conventions are invisible**. The 42
  overlap are rules duplicated into both representations during migration.

## Work items

### (c) DONE — `atdd author` emits the full field set  (commit 03008b2f)
`create_convention_node` was behind the schema (6–7 fields). Now emits all 15 schema
properties when provided: `name, implementation, source, content, bidirectional,
metadata, parity` (+ existing). CLI flags added (`--implementation/--content/
--metadata/--node-source/--bidirectional/--parity`, JSON-validated). Field order
preserved (spec §5.1: rationale→terms→notes). Existing author tests green.

### (a) PROTOTYPED — single-node ingestion in graph_loader  (NOT yet landed)
A two-pass loader (blocks first, then single-node files, skip-if-id-already-loaded to
avoid migration-overlap false duplicates) makes all authored nodes visible:
- rule nodes **152 → 270** (+118 authored), uniqueness clean **0**, roundtrip clean **0**.
- **BLOCKER:** the binding sentinel goes to **4 violations** because single-node
  `implementation.ref` is **heterogeneous** — some refs are `file::test` (resolvable),
  but others are **rule-id cross-references** (e.g. `…hermetic-fake-must-declare-contract`)
  or **bare function names** (`test_train_files_exist_for_registry_entries`) that do not
  resolve to a validator stem. Landing the loader as-is turns the binding clean baseline
  red.
- **Decision:** reverted; ingestion is gated on ref normalization (below).

### (a-fix) Normalize `implementation.ref` before ingestion lands
Either (i) normalize authored `implementation.ref` to a single binding form
(`module::function` where module ∈ validator stems), or (ii) teach
`declaration_to_implementation_binding` to resolve the single-node ref variants
(rule-id cross-ref → the rule that binds it; bare function → owning module). Then land
the two-pass loader with binding clean baseline = 0.

### (d) `atdd author` should scaffold an executable variant
Today author creates the rule node but **not** the convention-graph validator that
enforces it. Extend author (or `atdd plan`'s author pass) to also scaffold/register a
family/template **variant** under `src/atdd/validators/conventions/<family>/` so a newly
authored convention is actually enforced by the engine — not just declared.

### (e) Wire `conventions/` into the CI gate (prerequisite for decommission)
`atdd-validate.yml` runs only the persona paths (`{planner,tester,coder,coach}/
validators/`), NOT `src/atdd/validators/conventions/`. Add a "Run convention
validators" job so the new layer gates. **No legacy validator may be decommissioned
until this lands** (else coverage silently drops to zero).

## Sequencing

1. (e) CI gate job — convention layer must actually gate.  ← unblocks decommission
2. (a-fix) normalize `implementation.ref`; then (a) land single-node ingestion
   (binding baseline stays 0) → engine sees all 158 authored conventions.
3. (d) author scaffolds variants → new conventions are born enforced.
4. Then resume Tier-1 legacy decommission (family-parity-report.md) with operator sign-off.

Until (e)+(a) land, the engine's view of the convention graph is **incomplete by 116
nodes**, so "comprehensive parity/decommission" is not yet true and remains BLOCKED.
