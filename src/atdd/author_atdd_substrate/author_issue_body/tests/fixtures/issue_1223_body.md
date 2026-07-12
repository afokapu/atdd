## Issue Metadata

| Field | Value |
|-------|-------|
| Date | `2026-06-25` |
| Status | `INIT` |
| Type | `implementation` |
| Branch | `feat/issue-schema-json` |
| Archetypes | planner, coach |
| Train | `0003-author-substrate` |
| Feature | `feature:author-atdd-substrate:author-issue-body` |

> **Parent:** #1221 (Schema-Driven Authoring). **Sibling:** #1193 (author validates against canonical schema). **Coordinates with:** #1203 (State-Store-authoritative work-item lifecycle), #1168 (State Store). **Supersedes/augments:** the string-grep template gate (validator E019, `src/atdd/coach/commands/issue_template.py`).

---

> **NARROWED (systemic review, preserved from prior enrichment):** this was over-scoped as a State-Store umbrella; that work is already owned by **#1203** (State-Store-authoritative lifecycle) and provider-agnostic GitHub sync is **already done** (#1184 + #1201). This issue is now ONLY the issue **body** (shape/content) — a concrete **child of #1221** (schema-driven authoring) applied to the issue artifact. Lifecycle/state/sync are explicitly out of scope here.

## Scope

### In Scope

- **`issue.schema.json`** — a new canonical JSON Schema under `src/atdd/planner/schemas/author/` (alongside `convention-node`, `gate`, `relationship`, `scope`), modeling the *issue body* as a structured data artifact. It formalizes — as a schema — what the markdown `PARENT-ISSUE-TEMPLATE.md` + the E019 string-grep gate enforce today:
  - `## Issue Metadata` (Date, Status `enum`, Type `enum`, Branch, Archetypes, Train, Feature)
  - `## Scope` (In / Out / Dependencies / Done-when)
  - `## Context` (Problem Statement, User Impact, Root Cause)
  - `## Architecture` incl. **required** `### Graph Context` + `### Mirror Across Agents` (the two H3 subsections E019 lifted from advisory to mandatory in #682), Existing Patterns, Conceptual Model
  - `## Phases`, `## Validation` (Gate Tests + Success Criteria), `## Decisions`, `## Activity Log`, `## Artifacts`, `## Release Gate`, `## Notes`
  - per-property `description` (operator help), `required`, `type`, `enum` — modeled on `convention-node.schema.json` so `atdd author` consumes it identically.
- **`atdd author issue`** — a new `atdd author` subcommand (peer of `convention-node`/`gate`/`relationship`/`scope`) that produces a **schema-valid issue body** by construction (Graph Context present, no placeholders), generated from `issue.schema.json` via the #1221 `schema → argparse` mapper. Ends the manual body-patching seen across #1213–#1223.
- **A schema-driven validator** that checks an issue body against `issue.schema.json`, **superseding/augmenting** the string-grep compliance check (`issue_template.py`, validator E019). The schema becomes the single source of truth for "what sections/fields an issue body must contain"; the validator projects the schema rather than maintaining a parallel `PLACEHOLDER_STRINGS`/`REQUIRED_SUBSECTIONS` list.
- **Drift-guard test** (keystone, mirrors the #1221 author drift-guard and `convention-node`'s `_NODE_REQUIRED` parity): assert the issue-body generator's emitted fields == `issue.schema.json` `properties`, **and** that the schema's required sections == the H2/H3 set E019 enforces — so schema, generator, and gate can never drift.
- **Migration / back-compat path** from the markdown template to the schema: existing GitHub issue bodies (unstructured markdown) must continue to validate (or be mechanically migrated) — the schema must accept today's compliant bodies, not just newly-authored ones.
- Retire `atdd issue`'s bespoke **body-templating** (the hand-written template-string render of `PARENT-ISSUE-TEMPLATE.md`) in favour of schema-driven generation, OR retrofit `atdd issue` to call `atdd author issue` internally (see Decisions #1).

### Out of Scope

- Work-item **lifecycle / state** + State-Store SoT cutover → **#1203** (route `atdd issue` reads/writes through the store; store authoritative for status/phase/bindings/GitHub refs). This issue owns body **shape**, not where the work item is stored.
- Provider-agnostic GitHub **sync** → already **DONE** (#1184 / #1201).
- "Lifecycle → coach" re-homing of the `atdd issue` command → a decision raised on **#1203**, not here.
- The generic `schema → argparse` mapper itself → owned by **#1221**; this issue *consumes* it for the issue kind.
- Cross-field / semantic rules JSON Schema can't express (e.g. "Branch matches an `atdd branch` worktree", GraphQL label derivation) — those **stay in code** (per #1221's split: schema owns shape + docs; code owns policy).

### Dependencies

- **#1221** (schema-driven authoring engine: the `schema → argparse` mapper + drift-guard pattern) — prerequisite for the generator wiring; can proceed in parallel for the schema-authoring part.
- **#1193** (sibling) — `atdd author` validating against the canonical schema; once landed, `atdd author issue` inherits real schema validation rather than a hand-rolled required-field subset.
- **#1203 / #1168** (coordination, not blocking) — the body schema must align with how the State Store stores work items so the two do not fork (see Decisions #4 + Notes Review Pass 2).

### Done-when

- New issue bodies are generated from `issue.schema.json` (Graph Context + Mirror present by construction); the bespoke template-string render is gone (or delegated); the drift-guard test is green; existing compliant bodies still validate; the schema-driven validator supersedes/augments E019 with the same required-section coverage, mechanically cross-checked.

---

## Context

### Problem Statement

| Aspect | Current | Target | Issue |
|--------|---------|--------|-------|
| Issue body representation | unstructured **markdown** rendered from `PARENT-ISSUE-TEMPLATE.md` | a **schema-valid data artifact** governed by `issue.schema.json` | the issue is the one substrate artifact with no canonical schema |
| Body validation | **string checks** — `issue_template.py`/E019 greps for required H2/H3 headings + a literal `PLACEHOLDER_STRINGS` blacklist | schema validation (`type`/`enum`/`required`/`properties`) like every other `atdd author` kind | string-grep is brittle (placeholder cat-and-mouse), can't validate field *shape*, and is a parallel surface that drifts from the template |
| Body authoring | `atdd issue <slug>` renders a hand-written template string, then bodies are **manually patched** to add Graph Context etc. | `atdd author issue` emits a compliant-by-construction body from the schema | manual patching across #1213–#1223 was pure drift-tax |
| Substrate parity | `convention-node`, `gate`, `relationship`, `scope` are schema-authored + schema-validated | the issue artifact joins them | issues can't be authored/validated/migrated like the rest of the substrate, blocking #1221 and the #1203 work-item lifecycle |

### User Impact

Authors get a compliant-by-construction issue body (Graph Context + Mirror present, no placeholder traps) with `--help` sourced from the schema, the same ergonomics as `atdd author convention-node`. Reviewers get a single, mechanically-checked definition of "a valid issue body" instead of a string-grep that authors learn to game. The substrate gains the missing artifact schema that #1221 generalizes over and #1203 can align its State-Store work-item record to.

### Root Cause

The issue body predates the `atdd author` schema substrate. Compliance was bolted on as a markdown template (`PARENT-ISSUE-TEMPLATE.md`, #682 added the mandatory Graph Context/Mirror H3s) policed by a runtime string parser (`issue_template.py`, SPEC-COACH-ORCH-0010/0011, validator E019) — a *string* contract, not a *data* contract. Every other authored artifact moved to `<kind>.schema.json`; the issue never did. #1221 (schema-driven authoring) makes finishing that migration cheap and removes the manual-patch drift class.

---

## Architecture

### Graph Context

- **Child of #1221** (schema-driven authoring), applied to the *issue* artifact. The schema owns the issue body's **shape**; lifecycle/state belong to **#1203** + coach; persistence to the State Store (**#1168**).
- **New schema:** `src/atdd/planner/schemas/author/issue.schema.json` — modeled on `convention-node.schema.json` (`$schema` draft-07, `$id: atdd:author:issue:1.0.0`, `required` top-level section keys, per-property `description`, `enum` for Type/Status). It becomes the source of truth that (a) the body generator emits against, (b) the schema-driven validator checks against, and (c) the drift-guard test pins.
- **Generator:** a new `create_issue_body(spec, ...)` + `atdd author issue` subparser in `src/atdd/planner/commands/author.py` (peer of `create_convention_node` / the `convention-node` subparser at `author.py:451`), built via the #1221 `schema → argparse` mapper. Emits sections in schema property order, mirroring how `create_convention_node` emits in `convention-node.schema` order (`author.py:174`).
- **Validator move:** the string-grep gate in `src/atdd/coach/commands/issue_template.py` (`load_required_sections` / `check_body_sections` / `check_placeholders`, bound by E019 in `src/atdd/coach/validators/test_issue_validation.py`) is re-expressed as a schema check against `issue.schema.json`. The planner `planner.issue-body.graph-context-required` rule (today keyed off the literal Graph Context placeholder, `issue_template.py:54-57`) re-binds to the schema's required `### Graph Context` property.
- **Boundary (do NOT duplicate):** work-item **lifecycle/state + State-Store SoT cutover = #1203**; provider-agnostic GitHub **sync = DONE (#1184/#1201)**; "lifecycle → coach" re-homing = a decision raised on **#1203**, not here.

### Mirror Across Agents

| Agent | Current state | Target state | Action |
|-------|---------------|--------------|--------|
| planner | authors `convention-node`/`gate`/`relationship`/`scope` via schemas; **no** `issue.schema.json`; `author.py` has no issue kind | owns `issue.schema.json` + `atdd author issue` (generator via the #1221 mapper) | **add** schema + subcommand + `create_issue_body` |
| coach | `atdd issue <slug>` renders the markdown template string; `issue_template.py` string-greps the body; E019 gates compliance | `atdd issue` delegates to / is superseded by schema-driven generation; the gate validates against `issue.schema.json` | **update** issue command + retire bespoke template render; re-express the gate as schema validation |
| tester | E019 (`test_issue_validation.py`) asserts required-section *strings* + placeholder blacklist | E019 asserts schema validity; **new drift-guard** test (generator fields == schema properties == E019 required sections) | **add** drift-guard; **rewire** E019 to the schema |
| coder (be) | n/a for body shape (State-Store work-item record owned by #1203) | ensure the #1203 work-item record and `issue.schema.json` share field names/enums (no fork) | **coordinate** field/enum alignment with #1203 |

### Existing Patterns

| Pattern | Example File | Convention |
|---------|--------------|------------|
| `<kind>.schema.json` as source of truth | `src/atdd/planner/schemas/author/convention-node.schema.json` | draft-07, `$id: atdd:author:<kind>:<ver>`, `required`, per-property `description` |
| schema-validated authoring | `src/atdd/planner/commands/author.py` (`create_convention_node`, `author.py:136`; subparser `author.py:451`) | author validates against the schema, emits in property order, never writes a partial artifact |
| schema-driven CLI + drift-guard | #1221 `schema → argparse` mapper | accepted-arg set == schema `properties`; `--help` from `description` |
| string-grep compliance (being replaced) | `src/atdd/coach/commands/issue_template.py` | `load_required_sections`/`check_body_sections`/`check_placeholders`; SPEC-COACH-ORCH-0010/0011; E019 |
| local SoT, GitHub a projection | #945, #1171, #1203 | the schema/store is authoritative; the rendered body/GitHub is a projection |

### Conceptual Model

| Term | Definition | Example |
|------|------------|---------|
| issue body schema | the canonical JSON Schema for an issue body's shape | `issue.schema.json` |
| compliant-by-construction | a body authored from the schema is valid without post-hoc patching | `atdd author issue` output passes the gate immediately |
| drift-guard | a test asserting generator fields == schema properties == gate required-sections | fails if a section is added to one surface but not the others |
| schema-driven gate | the compliance validator projects the schema instead of greping strings | E019 loads `issue.schema.json`, not `PLACEHOLDER_STRINGS` |
| body-as-projection | the markdown body rendered from structured data (schema-shaped) | render(structured_issue) → GitHub markdown |

### Before State

```
atdd issue <slug>
  └─> render PARENT-ISSUE-TEMPLATE.md (hand-written template string)
        └─> GitHub markdown body (unstructured)
              └─> E019 / issue_template.py: grep H2/H3 + PLACEHOLDER_STRINGS blacklist  (STRING contract)

src/atdd/planner/schemas/author/: convention-node, gate, relationship, scope     (NO issue.schema.json)
```

### After State

```
src/atdd/planner/schemas/author/issue.schema.json   (DATA contract — single source of truth)
        ├─> atdd author issue  (schema → argparse mapper, #1221)  → schema-valid body by construction
        ├─> E019 / gate: validate body against issue.schema.json  (supersedes string-grep)
        └─> drift-guard test: generator fields == schema properties == gate required-sections

atdd issue <slug>  → delegates to / superseded by atdd author issue   (Decision #1)
existing markdown bodies  → still validate (back-compat) / mechanically migrated   (Phase 4)
```

---

## Phases

### Phase 1: Author `issue.schema.json`

**Deliverables:**
- `src/atdd/planner/schemas/author/issue.schema.json` — top-level required section keys + per-property `description`, `type`, `enum` (Status, Type), modeled on `convention-node.schema.json`. The required set MUST equal the H2 sections in `PARENT-ISSUE-TEMPLATE.md` plus the H3 `### Graph Context` / `### Mirror Across Agents` (the E019 `REQUIRED_SUBSECTIONS`).
- A schema-vs-template parity assertion (the schema's required sections derive from / match `load_required_sections()` + `REQUIRED_SUBSECTIONS`).

**Files:**

| File | Change |
|------|--------|
| `src/atdd/planner/schemas/author/issue.schema.json` | **new** — the canonical issue-body schema |
| `src/atdd/planner/schemas/author/tests/…` | **new** — schema validity + required-section parity test |

### Phase 2: `atdd author issue` generator

**Deliverables:** `create_issue_body(spec, ...)` + an `atdd author issue` subparser generated from the schema via the #1221 mapper; emits a compliant-by-construction body (Graph Context + Mirror present, no placeholders) in schema property order.

**Files:**

| File | Change |
|------|--------|
| `src/atdd/planner/commands/author.py` | **add** `create_issue_body` + `issue` subparser (peer of `convention-node`) |
| `src/atdd/planner/commands/tests/…` | **add** generator tests (valid output passes the gate) |

### Phase 3: Schema-driven gate + drift-guard

**Deliverables:** re-express the E019 compliance check as validation against `issue.schema.json`; re-bind `planner.issue-body.graph-context-required` to the schema's required Graph Context; add the keystone drift-guard test (generator fields == schema properties == gate required-sections).

**Files:**

| File | Change |
|------|--------|
| `src/atdd/coach/commands/issue_template.py` | route required-section/placeholder logic through `issue.schema.json` (retire parallel `PLACEHOLDER_STRINGS`/`REQUIRED_SUBSECTIONS` as the source of truth) |
| `src/atdd/coach/validators/test_issue_validation.py` | E019 validates against the schema |
| `src/atdd/planner/commands/tests/…` | **new** drift-guard test |

### Phase 4: Migration / back-compat + retire bespoke template

**Deliverables:** existing GitHub issue bodies validate against `issue.schema.json` (or a one-shot mechanical migrator); the hand-written `PARENT-ISSUE-TEMPLATE.md` render in `atdd issue` is removed or delegated to `atdd author issue` (Decision #1). The markdown template file is kept as a human-readable projection if needed, regenerated from the schema (no second source of truth).

**Files:**

| File | Change |
|------|--------|
| `src/atdd/coach/commands/issue.py` | delegate body generation to schema-driven path |
| `src/atdd/coach/templates/PARENT-ISSUE-TEMPLATE.md` | regenerated-from-schema projection (or removed) |
| (migration test) | sample of existing compliant bodies validate against the schema |

---

## Validation

### Gate Tests

| ID | Phase | Command | Expected | ATDD Validator | Status |
|----|-------|---------|----------|----------------|--------|
| GT-001 | design | `atdd validate coach` | PASS | `src/atdd/coach/validators/test_issue_validation.py` | TODO |
| GT-002 | design | `atdd registry update --check --scope changed-files` | PASS | `src/atdd/coach/commands/registry.py` | TODO |
| GT-100 | impl | `atdd author issue …` emits a body that passes the gate | PASS | new generator test | TODO |
| GT-110 | impl | drift-guard: generator fields == `issue.schema.json` properties == E019 required sections | PASS | new drift-guard test | TODO |
| GT-120 | impl | sample existing compliant bodies validate against `issue.schema.json` | PASS | migration test | TODO |
| GT-800 | completion | `atdd repo validate` | PASS | `src/atdd/coach/validators/test_urn_traceability.py` | TODO |
| GT-850 | completion | `atdd registry update --check` | PASS | `src/atdd/coach/commands/registry.py` | TODO |
| GT-900 | completion | `atdd validate` | PASS | `src/atdd/` | TODO |

### Success Criteria

- [ ] An issue body **validates against `issue.schema.json`** (the artifact is a data contract, not a string contract).
- [ ] `atdd author issue` **emits a schema-valid body that passes the compliance gate** with Graph Context + Mirror present and **zero placeholders**, no manual patching.
- [ ] **Existing compliant issue bodies migrate/validate** against the schema (back-compat — the schema accepts today's bodies, not only newly authored ones).
- [ ] The schema **captures the same required sections E019 enforces, mechanically cross-checked** by the drift-guard test (schema properties == `load_required_sections()` + `REQUIRED_SUBSECTIONS`).
- [ ] Adding/removing a required section changes the schema, the generator output, and the gate **with no parallel hand-edit** (drift-guard fails otherwise).
- [ ] The bespoke `PARENT-ISSUE-TEMPLATE.md` template-string render is removed or delegated; `PARENT-ISSUE-TEMPLATE.md`, if kept, is a regenerated projection.
- [ ] `atdd validate` / `atdd repo validate` green; no behaviour regression in `atdd issue`.

---

## Decisions

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| 1 | Retrofit `atdd issue` to emit schema-valid bodies, or supersede it with `atdd author issue`? | **Retrofit** — `atdd issue` keeps its lifecycle UX (slug → GitHub issue) but delegates **body generation** to the schema-driven path; `atdd author issue` is the underlying authoring primitive. | Avoids breaking the operator-facing `atdd issue <slug>` flow and the prohibition on `gh issue create`; the lifecycle command stays, only its body source changes. Final say coordinates with #1203 (which owns where the work item is stored). |
| 2 | Deprecate `PARENT-ISSUE-TEMPLATE.md`? | **Keep as a regenerated projection** (or remove if no consumer needs the markdown) — it is **not** a second source of truth. | The schema is authoritative; a human-readable markdown projection can be regenerated. Mirrors #1203's "manifest is a projection" stance. |
| 3 | Schema owns semantic rules (Branch↔worktree, GraphQL label derivation)? | **No** — schema owns shape + docs; semantic/operational rules stay in code. | The #1221 split: JSON Schema can't express cross-field/path/label policy; keep it in `validate_*`. |
| 4 | Align `issue.schema.json` field names/enums with the #1203 State-Store work-item record? | **RESOLVED — single shared vocabulary (no fork).** `issue.schema.json` is the canonical definition of the body's field names + Status/Type enums; the #1203 State-Store work-item record reuses the SAME vocabulary. Evidence: the store does not define its own enums — `manifest_import.py` sets the work-item `state` straight from the manifest `status` field (`_STATE_KEY="status"`), keys the object by `slug`, records the GitHub issue as an `external_ref`, and keeps archetype/train/feature in an opaque `data` blob (`store.py` `Object(uid,kind,state,data)`). Status values are exactly the phase-machine labels. So body, store, and GitHub projection already share one vocabulary de facto; the schema's `Status` enum derives from `phase_machine.convention.yaml` (single SoT) and #1203 references it. | Forking would require inventing a divergent vocabulary that does not exist today; aligning keeps status/phase/type identical across body, store, and GitHub. |
| 5 | Where does the issue *kind* live — planner `author` or coach? | **planner `author`** (schema + generator), coach **consumes** it in `atdd issue`. | Parity with the other authored kinds, all under `planner/schemas/author/` + `planner/commands/author.py`; coach owns lifecycle, not artifact shape. |

---

## Activity Log

### Entry 1 (2026-06-25)

**Completed:**
- Filed (thin) and narrowed via systemic review to issue **body shape only** (lifecycle → #1203, sync done #1184/#1201).

### Entry 2 (2026-06-29)

**Completed:**
- Three-pass staff review + enrichment to implementation-ready (this body). Confirmed the capability gap: `src/atdd/planner/schemas/author/` has `convention-node`/`gate`/`relationship`/`scope` and **no `issue.schema.json`**; the only `issue*.schema.json` files are coach review-pass schemas, unrelated to issue bodies. Confirmed the body is governed by the markdown template + the E019 string-grep gate, not a schema.

**Next:**
- `atdd branch <N>` → Phase 1 (`issue.schema.json`), then Phases 2–4. Raise the #1203 field/enum-alignment decision (Decisions #4) before finalizing the schema.

---

## Artifacts

### Created

- `src/atdd/planner/schemas/author/issue.schema.json` (Phase 1)
- `atdd author issue` generator + tests (Phase 2)
- drift-guard test (Phase 3)
- migration/back-compat test (Phase 4)

### Modified

- `src/atdd/planner/commands/author.py` (add issue kind)
- `src/atdd/coach/commands/issue_template.py` + `src/atdd/coach/validators/test_issue_validation.py` (E019 → schema)
- `src/atdd/coach/commands/issue.py` (delegate body generation)
- `src/atdd/coach/templates/PARENT-ISSUE-TEMPLATE.md` (projection or removed)

### Deleted

- (pending — bespoke template-string render path, if fully superseded)

---

## Release Gate

INTERIM (see #1172): bump the version manually. The bump-on-merge automation (`post-merge-lifecycle.yml`) is NON-OPERATIONAL (direct push to main rejected by branch protection GH006). `publish.yml` tags + publishes from the version on main.

- [ ] Rebase on main: `git pull origin main --rebase`
- [ ] Bump version (feat/ → **MINOR** — new schema + new `atdd author issue` subcommand + new validator): edit `pyproject.toml`, commit "Bump version to X.Y.Z"
- [ ] Merge PR → `publish.yml` tags + publishes from the version on main
- [ ] Do NOT rely on post-merge auto-bump (broken; superseded by #1172)

---

## Notes

The issue body is the last `atdd author` artifact without a schema; closing this gap is what makes #1221 (schema-driven authoring) actually general across all substrate kinds, and gives #1203 a schema to align the State-Store work-item record to.

### Review Log

**Pass 1 — systemic (trace schema → author → validate → migrate → State-Store alignment).**
- Traced the full chain. The thin spec named the schema, the generator, and the drift-guard but **omitted the validate and migrate links** and left "supersede E019" implicit. Fixes applied: (a) added an explicit **schema-driven validator** scope item + Phase 3 re-expressing E019 (`issue_template.py` / `test_issue_validation.py`) against the schema, naming the exact functions (`load_required_sections`/`check_body_sections`/`check_placeholders`) and the `planner.issue-body.graph-context-required` rule that re-binds; (b) added a **migration/back-compat** scope item + Phase 4 + GT-120 so existing markdown bodies still validate (the thin spec only covered *new* bodies); (c) made the **drift-guard tri-directional** — generator fields == schema properties == E019 required sections — not just generator-vs-schema, closing the gap where the schema could drift from the gate. The chain now has no missing link.

**Pass 2 — plan-fit (child of #1221, sibling of #1193, coordinating with #1203/#1168).**
- Confirmed **child of #1221**: #1221's body lists #1223 as its child and #1221 owns the `schema → argparse` mapper this consumes — added that as an explicit dependency (the generator wiring needs the mapper). Surfaced **#1193 as sibling**: once #1193 lands (author validates against the canonical schema), `atdd author issue` inherits real schema validation instead of a hand-rolled subset — noted in Dependencies. Verified **non-collision with #1203/#1168**: #1203's own body explicitly partitions "#1223 owns the body; #1203 owns lifecycle/state + State-Store SoT." Strengthened the boundary in Scope/Out + Graph Context, and — the one substantive plan-fit risk — promoted the **schema↔store field/enum alignment** to **Decision #4** with an explicit open question (below), so the body schema and the State-Store work-item record do not fork. Archetypes set to **planner + coach** (planner owns schema/generator, coach owns the gate + `atdd issue`), per Decision #5.

**Pass 3 — comprehensiveness (measurable AC, non-goals/risks, Graph Context + Mirror, no implementer blockers).**
- All success criteria rewritten to be **measurable** (validates-against-schema; emits-passing-body-with-zero-placeholders; existing-bodies-validate; drift-guard mechanically cross-checks schema==gate). **Non-goals** made explicit (lifecycle/state #1203, sync done, the mapper itself #1221, semantic rules stay in code). **Risks/decisions** captured in the Decisions table (retrofit vs supersede `atdd issue`; deprecate template; schema-vs-store alignment). **Graph Context + Mirror Across Agents** both present and concrete (real file paths + line anchors: `author.py:136/174/451`, `issue_template.py:54-57`). Added Before/After state diagrams and a Conceptual Model so a future implementer has no blockers. Phases are sequenced and each carries files + gate tests.

### Resolved coordination decision (with #1203 / #1168)

**Decision: single shared vocabulary — `issue.schema.json` owns the body shape and is the canonical definition of the field names + Status/Type enums; the #1203 State-Store work-item record reuses them. They do NOT fork.** Evidence from the live State Store: it defines no competing enum vocabulary — `src/atdd/state/manifest_import.py` writes each work item via `store.objects.upsert(slug, "work_item", state=<manifest status>, data=<rest>)` (`_IDENTITY_KEY="slug"`, `_STATE_KEY="status"`), records the GitHub issue number as an `external_ref(provider="github", ref_kind="issue")`, and keeps archetype/train/feature/branch in the opaque `data` blob; `src/atdd/state/store.py` models the object as `Object(uid, kind, state, data)` with `state` a free-form `Optional[str]`. The `status` values are the phase-machine labels (INIT/PLANNED/RED/GREEN/SMOKE/REFACTOR/COMPLETE/BLOCKED/OBSOLETE). #1203's own body reaffirms the partition ("#1223 owns the body; #1203 owns lifecycle/state + State-Store SoT"). **Constraint on this work:** the schema's `Status` enum derives from `src/atdd/coach/conventions/phase_machine.convention.yaml` (the single source of truth for phase values) so body, store, and GitHub projection stay identical; the schema must not introduce a divergent Status/Type vocabulary. (Made testable by WMBT C010-UNIT-002: a Metadata `Status` outside the phase enum is rejected.)


