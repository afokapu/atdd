# Proposal for review — correcting three drifted `*.definition` convention nodes (ATDD #2039)

You are one of three independent reviewers. Be adversarial. I want disagreement where
I am wrong, not endorsement. Answer the four questions at the end directly.

## Background

The ATDD repo defines plan artifacts twice: a JSON Schema per artifact kind
(`src/atdd/planner/schemas/*.schema.json`) and an advisory prose "definition" node per
kind (`src/atdd/planner/conventions/nodes/planner.<kind>.definition.convention.yaml`).

Nothing validates the second against the first. All seven definition nodes are
`status: draft`, `kind: family`, self-described "advisory semantic anchor — it enforces
nothing directly", with **zero** entries in `.atdd/binding.lock.yaml`. The repo validates
artifact SHAPE exhaustively (`test_wmbt_vocabulary`, `test_hierarchy_coverage`,
`test_wmbt_has_smoke_acceptance`, `test_wmbt_consistency`, per-acceptance schema
validation) and has never validated that its own DEFINITIONS describe that shape.

I audited all seven. Three drifted; three are clean; one has no schema to drift from.

## Measured evidence

```
Acronym expansions of "WMBT" in tracked source:
  "What Must Be True"              12 files  (schemas, conventions, label taxonomy, rule_binding.py)
  "What-Might-Break Test"           1 file   planner.wmbt.definition.convention.yaml:6
  "Write Meaningful Before Tests"   1 file   coach/commands/inventory.py:514
  "Way My Brain Tests"              0 files in source (graphify-out/ only — generated, untracked)

WMBT corpus, by direction (484 total):   minimize 397 (82%)   maximize 87 (18%)

feature files (190 total):
  urn 190/190   wagon 190/190   wmbts 190/190
  description 187   sizing 187   components 187
  status 0/190      acceptance 0/190

feature.schema.json properties (additionalProperties-constrained):
  appendices, components, description, ioSeeds, sizing, urn, wagon, wmbts
  required: urn, wagon, description, sizing, wmbts, components

wmbt.schema.json:
  required: urn, step, direction, dimension, object_of_control, lens
  step enum:      define locate prepare confirm execute monitor modify resolve conclude  (D L P C E M Y R K)
  direction enum: minimize maximize increase decrease
  dimension enum: time effort likelihood frequency quantity "financial value"
  `acceptances` is a PROPERTY, typed $ref acceptance.schema.json#/definitions/embedded_acceptance
  description: "Schema for What Must Be True statements that define measurable outcomes"

train-interlocking.schema.json:
  route required: route_id, category, priority, guard_ref, train_id, train_path, projection
  guard required: id, expression   (operators: == != < <= > >= and or not exists(field))
  live guards: exists(overlay_events) ; bound == true and violations == 0

atdd coach inventory (coach/commands/inventory.py):
  :514  docstring expands WMBT as "Write Meaningful Before Tests"
  :520  comment "WMBT categories: C (Contract), L (Logic), E (Edge), P (Performance)"
  :521  wmbt_patterns = {"contract":"C","logic":"L","edge":"E","performance":"P"}
  :534  glob(f"**/{prefix}[0-9]*.yaml")     <- the comment IS the glob
  measured: counts 334 of 484 WMBTs, missing 150 (31%) — D:74 Y:29 R:20 M:19 K:8
```

## Current text (verbatim)

**A. `planner.wmbt.definition.convention.yaml`**
> A WMBT (What-Might-Break Test) is a falsifiable statement of a single way an artifact
> might break — scoped to one object of control along one dimension, direction, and lens —
> declared with an id and a statement, and paired with the acceptances that prove it,
> including at least one smoke acceptance.

**B. `planner.feature.definition.convention.yaml`**
> A feature is the smallest independently-verifiable slice of a wagon's behavior — a
> bounded capability that declares a URN, a status, and a non-empty acceptance section,
> links to exactly one wagon, closes a feedback loop, and stays within its size limits.

**C. `planner.interlocking.definition.convention.yaml`**
> An interlocking is the domain-decomposition artifact for a diverging journey — it
> declares WHICH train is selected next when a journey branches, keyed by a produced
> artifact (the divergence signal), composing multiple strictly-linear trains into a
> branching journey.

## My argument that the schema is authority (not preference)

1. **Structural.** `acceptances` is a child *property* of a WMBT. A thing that HAS
   acceptances is not itself an acceptance criterion.
2. **Internal precedent.** The sibling node `planner.wmbt.shape` is already correct: a WMBT
   declares "its statement, and the artifacts that prove the statement", glossing
   `proving_artifacts` as "the acceptances/tests that PROVE the WMBT statement."
3. **Falsification.** "A way an artifact might break" cannot describe a `maximize` WMBT.
   87 of 484 are `maximize` — e.g. "maximize likelihood of a reproducible
   installed-substrate…". The break-framing covers at most the `minimize` 82%.
4. **For the feature node:** `status` and `acceptance` appear in neither the schema nor
   any of 190 files. The definition instructs authors to produce an invalid artifact.

## Proposed replacements

**A. WMBT**
> A WMBT (What Must Be True) is a single measurable outcome that must hold for a wagon's
> job to be done — it names one `object_of_control`, moved in one `direction` along exactly
> one `dimension`, at one `lens`, qualified by a `context_clarifier` and placed at one JTBD
> `step`; its `statement` is composed as `{direction} {dimension} of {object_of_control}
> [context_clarifier]`. A WMBT is not itself a test or an acceptance criterion: the
> `acceptances` it carries are the artifacts that prove it, of which at least one must be a
> SMOKE acceptance.

**B. Feature**
> A feature is the smallest independently-verifiable slice of a wagon's behavior — a bounded
> capability that declares a `urn`, links to exactly one `wagon`, carries a `description`,
> declares the `wmbts` it covers, and states its `sizing` and `components`.

**C. Interlocking**
> An interlocking is the domain-decomposition artifact for a diverging journey — it declares
> WHICH linear train is selected next when a journey branches, each route selected by a
> declarative `guard` expression over observable fields and resolved under an explicit
> `route_resolution.strategy`, composing multiple strictly-linear trains into a branching
> journey.

Plus mechanical corrections: four coach sites calling a WMBT an "acceptance criterion" /
"criterion" → "measurable outcome" (`coach/conventions/issue.convention.yaml:38,197,601`,
`coach/schemas/label_taxonomy.schema.json:94`, `coach/utils/rule_binding.py:145`); and
`inventory.py` gets the right expansion and all nine step codes with the schema's meanings.

## Scope decisions I made (challenge these)

- **Not binding the definition nodes.** All seven are `draft`/`family` with no lock entry.
  Promoting them to bound rules is a substrate act with a different approval path. Instead
  I add an acceptance that fails when a definition node names a field its schema does not
  declare. **Is that too weak?**
- **Leaving `wagon`/`train`/`artifact` definitions alone** — checked, accurate.
- **`theme`** — no `theme.schema.json` exists, so its "single-digit (0-4)" claim is not
  assessable against a schema. Left alone.
- **"Way My Brain Tests"** treated as a graphify artefact, not a source defect.

## Answer these four, directly

1. Is "measurable outcome" the right head-noun for a WMBT, given the schema fields and the
   `direction`/`dimension` enums? If not, what is — and why is it better?
2. Is my structural argument (`acceptances` is a child property, therefore a WMBT is not an
   acceptance criterion) sound, or am I over-reading a JSON-Schema nesting choice?
3. Is the proposed feature definition right to drop "closes a feedback loop" and "stays
   within its size limits" — claims the schema does not express as fields, though `sizing`
   exists? Or should prose keep intent the schema cannot encode?
4. Is an acceptance that checks "definition node names no field absent from its schema"
   sufficient to stop recurrence, or is it theatre without binding the nodes?

Be specific. Quote my text where you disagree.
