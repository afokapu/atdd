# Revised proposal after tri-review — ATDD #2039

Three independent reviewers (`claude -p`, `zcode -p`, `codex exec`). Every load-bearing
correction below was re-verified against the repo before acceptance.

## Corrections I accepted

| # | Correction | Raised by | Verified |
|---|---|---|---|
| 1 | `feature.schema.json` has **no root `additionalProperties`**. `status`/`acceptance` are not schema-rejected. My "instructs authors to produce an invalid artifact" reasoning was wrong. | all 3 | yes — a synthetic feature carrying both validates |
| 2 | Drop the nesting argument. Containment ≠ semantic category. | all 3 | conceded |
| 3 | "measurable outcome" overclaims — no unit, baseline, threshold or metric on a WMBT. It is a **statement**. | all 3 | schema: "…**statements** that define measurable outcomes" |
| 4 | **Keep** "stays within its size limits" — `planner.feature.size-max-rule` + `planner.feature.hard-limits` are `status: active`, and `sizing.footprint_size` is a schema field | all 3 | yes |
| 5 | **Conditionalize**, don't drop, the feedback-loop clause — the rule keys on `kind: feedback-loop` | all 3 | yes; `kind` is in 0/190 files and absent from the schema |
| 6 | `planner.feature.shape` is `kind: rule`, `status: active`, and says verbatim "declare a urn, **a status, and a non-empty acceptance section**" — the source of the drift | claude, zcode | yes |
| 7 | The `terms:` blocks repeat the same claims; WMBT's says "declares its **id**" — there is no `id`, it is `urn` | claude, zcode | yes |
| 8 | Extend the existing `test_definition_anchors.py` (`planner.definition.anchor-required`: active, strict, bound) rather than add a free-floating acceptance | claude, zcode | yes, file exists |
| 9 | Theme **is** assessable — `_theme_taxonomy.py` owns the digit→theme map. My exemption was wrong. | zcode | yes, file exists |
| 10 | "four coach sites" → **five locations across three files** | codex | yes |
| 11 | `plan_unit_schema.py`: `feature`/`wmbt` schemas are **advise**-tier (reject 134/188 features, 294/468 WMBTs); `wagon`/`train`/`interlocking`/`acceptance` are **enforce**-tier | zcode | yes |

## The one disagreement, and how it resolved

Reviewer 2 endorsed my interlocking rewrite. Reviewer 1 blocked it: `plan/_dispatch.schema.json`
is the **"Declared Dispatch Registry"**, whose description reads *"Maps a produced divergence
`artifact_urn` to the `train_id` that resolves it."*

Verified — the file exists and says exactly that. So "keyed by a produced artifact (the
divergence signal)" is **true of a real sibling artifact**, not drift. My replacement would have
deleted a true statement. **Reviewer 1 is right; reviewer 2 missed the file.**

C becomes **additive**: both mechanisms named. Reviewer 3 also corrected the mechanics — a route
*references* a declared guard (`guard_ref`), the expression lives under `fragments[].guards[]`.

## Authority, reframed

"The schema is authority" is **inverted for the two kinds I am correcting**. `plan_unit_schema.py`
puts `feature` and `wmbt` on the **advise** tier precisely because their schemas reject most real
files; the working authorities there are the Python validators plus the corpus. Issue #760 set the
precedent by changing the *schema* to match the *corpus*.

So the operative order is **corpus > validators > schema > prose** — which still condemns every
finding (`status` 0/190, the acronym, the 31% undercount) while no longer resting on a schema that
disclaims its own enforcement in its `$comment`.

## Revised replacements

**A. WMBT**
> A WMBT (What Must Be True) is a single directional outcome statement for a wagon's job — it
> names one `object_of_control`, moved in one `direction` along exactly one `dimension`, at one
> `lens`, optionally qualified by a `context_clarifier`, and placed at one JTBD `step`; its
> `statement` follows `{direction} {dimension} of {object_of_control} [context_clarifier]`
> (see `planner.wmbt.statement-template`). A WMBT is not itself a test: it is made measurable
> only by the `acceptances` that prove it, of which at least one must be a SMOKE acceptance.

**B. Feature**
> A feature is the smallest independently-verifiable slice of a wagon's behavior — a bounded
> capability that declares a `urn`, links to exactly one `wagon`, carries a `description`,
> declares the `wmbts` it covers, and enumerates its `components`; its `sizing` stays within
> the feature size limits (see `planner.feature.size-max-rule`, `planner.feature.hard-limits`),
> and a feature marked `kind: feedback-loop` closes that loop through its SMOKE evidence.

**C. Interlocking** (additive)
> An interlocking is the domain-decomposition artifact for a diverging journey — it declares
> WHICH linear train is selected next when a journey branches: each route references a declared
> `guard` expression (`guard_ref` → `fragments[].guards[]`) and is resolved under an explicit
> `route_resolution.strategy`, while the declared dispatch registry maps a produced divergence
> `artifact_urn` to the train that resolves it. Together they compose multiple strictly-linear
> trains into a branching journey.

## Scope, grown by the review

- **Add `planner.feature.shape`** (active rule, same false sentence) — the source, not the echo.
- **Patch the `terms:` blocks** on all touched nodes, including WMBT's `id` → `urn`.
- **Move the check into `test_definition_anchors.py`** and make it catch all three defect classes,
  not just absent-field: acronym canon; required-vs-optional; and semantic claims checked against
  named `validator_refs`. Reviewer 3's suggestion: give each definition machine-readable claims
  (`schema_ref`, field paths, required/optional, enum assertions, `validator_refs`) and check
  those, keeping prose as the human projection.
- **Cover theme** against `_theme_taxonomy.py` rather than exempting it.
- **Add an inventory-coverage regression guard** so the next step letter that gains files cannot
  silently re-drift.
- **`inventory.py` is a behaviour change, not a docstring fix**: `by_category` keys
  (`contract/logic/edge/performance`) are consumer-visible in `inventory[...]["by_category"]`, the
  total moves 334 → 484, and `scan_wmbt_acceptance` / "WMBT acceptance files" repeat the same noun
  error. Rename in the same change or the defect survives in the identifier.

## Findings the review surfaced that I had missed

- `issue.convention.yaml:39` gives the WMBT `location:` as
  `plan/{wagon}/features/{feature}.yaml (wmbt section)`. WMBTs are standalone
  `plan/<wagon>/<STEP>NNN.yaml`; line 601 has it right. A wrong map is worse than a wrong noun.
- `issue.convention.yaml:32,36,40` point at `planner/conventions/{wagon,feature,wmbt}.convention.yaml`
  — that directory holds no such files; the nodes moved to `conventions/nodes/`.
- `kind` is consumed by an active feature validator and declared nowhere in `feature.schema.json`.
- 51 M + 9 L of 190 features (31.6%) exceed `max_size: S` — so restoring the size-limit clause
  restores the prose statement of a rule 60 artifacts currently break. Worth stating out loud.

## Still declined

- **Binding the definition nodes.** `binding.lock.yaml` has zero `planner.*` entries; the planner
  family enforces via the pytest validator suite. Extending `test_definition_anchors.py` needs no
  promotion. All three reviewers agreed declining was right.
- **"Way My Brain Tests"** — `graphify-out/` only, generated and untracked. Confirmed zero
  occurrences in tracked source.
