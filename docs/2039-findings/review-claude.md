Warning: no stdin data received in 3s, proceeding without it. If piping from a slow command, redirect stdin explicitly: < /dev/null to skip, or wait longer.
I pulled the actual repo (`/Users/alecfokapu/Github/atdd/main`, HEAD `36ce055a`) and re-measured everything before answering. Your corpus numbers are right. Two load-bearing claims in your evidence are not, and they change two of your four answers.

## Bottom line

The direction is correct on WMBT and half-correct on feature. The interlocking change is the one I'd block. And the biggest defect in the proposal isn't any of the three texts — it's that you're editing `statement:` on three `draft` nodes while leaving the identical false sentences in their `terms:` blocks and in the `status: active` rules those terms cite.

---

## First: two errors in your evidence

**1. `feature.schema.json` is not `additionalProperties`-constrained at the root.**

Your evidence block says "feature.schema.json properties (additionalProperties-constrained)". It isn't. Root keys are `$schema, title, description, type, required, properties, definitions` — no `additionalProperties`. Only `sizing`, `components`, `ioSeeds` and `componentEntry` are closed. I validated a synthetic feature carrying both `status:` and `acceptance:` against the real schema: **valid**.

So argument 4 — *"The definition instructs authors to produce an invalid artifact"* — is false as written. A file built to the current definition is invalid because it **omits** `description`, `sizing`, `wmbts`, `components` (4 of 6 required), not because `status` is forbidden. Fix the sentence; the conclusion survives, the reason doesn't.

This also matters downstream: your proposed acceptance ("definition node names a field its schema does not declare") is checking for a property the schema doesn't actually treat as an error.

**2. There are two interlocking-shaped routing artifacts, and you audited against one of them.**

```
plan/_dispatch.schema.json     "Declared Dispatch Registry" — artifact_urn -> train_id
plan/_dispatch.yaml            dispatch: []   (empty, awaiting divergence trains)
plan/_trains/_interlockings/   3 files, guard_ref + route_resolution.strategy
```

The current definition's *"keyed by a produced artifact (the divergence signal)… a declared routing registry (artifact_urn -> train_id)"* is a verbatim description of `_dispatch.schema.json`, not drift. And it's backed: `planner.train.dispatch-map-is-registry` and `planner.train.dispatch-composite-key-exceptional` both carry `disposition: strict`, `severity: 3`, and `implementation.ref: conventions/schema/test_dispatch_map_is_registry`. The node's own `terms.interlocking.values.artifact-keyed` cites both by name.

Your replacement text deletes the artifact key entirely. That would put the node's `statement:` in direct contradiction with its own `terms:` block (which you don't propose changing) and with two strict sibling rules that have validators. **This one should be additive, not substitutive** — the interlocking selects the next train by `guard` under `route_resolution.strategy`; the dispatch registry selects the resolving train by produced `artifact_urn`. Both exist. The definition currently names only the second; yours would name only the first.

Your measured evidence for C also undercounts: there are at least 9 guards across the 3 files, not the 2 you list (`documentation_verdict == "PASS"`, `same_object_divergence == true`, `guard:clean-gate`, `guard:strict-violation`, `guard:advisory-violation`, `guard:unbound-declaration`, `guard:succession-loss`, `guard:unrealized-obligation`, `exists(overlay_events)`). Both strategies are live: `fail_on_multiple_match` ×2, `first_priority` ×1.

---

## 1. Is "measurable outcome" the right head-noun?

**"Outcome" yes — it's the schema's own word, three times over, and you undersell that.** Your argument leans on `acceptances`-nesting when the schema hands you the noun directly:

- title: `"WMBT (What Must Be True) Schema"`
- description: `"...statements that define measurable outcomes"`
- `step`: `"...where in the job flow this outcome matters"`
- `direction`: `"Optimization direction indicating how to improve the outcome"`

**"Measurable" is an overclaim.** Nothing on a WMBT measures. There is no unit, baseline, target, or threshold field — `direction` + `dimension` give you a gradient with no scale. Measurability lives one level down, in the acceptance: `test_wmbt_acceptance_schema_honesty.py` documents §4.3 as "measurable by EITHER `harness.type` OR `signal.metric`+`threshold`". You can borrow the schema's adjective, but then the sentence should say where the measurement actually comes from.

**"Outcome that must hold" is a category slip.** Propositions hold; outcomes obtain. You get this friction because you're fusing two framings — "What Must Be True" (propositional) and "measurable outcome" (gradient). Pick the gradient one and let `acceptances` carry the truth-value:

> A WMBT (What Must Be True) is a single directional outcome for a wagon's job — one `object_of_control` moved in one `direction` along exactly one `dimension`, at one `lens`, qualified by a `context_clarifier` and placed at one JTBD `step`… made measurable only by the `acceptances` that prove it, of which at least one must be a SMOKE acceptance.

Two supporting checks: all 484 WMBTs carry `statement` and `context_clarifier` even though neither is in `required` — so naming them is right. And `increase`/`decrease` are in the `direction` enum but used 0 times; "moved in one direction" covers that without committing you to the dead enum members.

## 2. Is the structural argument sound?

**No. Drop argument 1.** Nesting is not semantics — a `Test` can own `assertions` and still be a test; an acceptance criterion could perfectly well carry proof artifacts as children. You're reading a containment relation as a type exclusion.

It's worse than merely weak here, because the schema disclaims itself:

> `"$comment": "This schema is NOT applied as a file-level gate to WMBT files… additionalProperties: false is retained as-is but is never enforced against files."`

You are arguing "the schema is authority, not preference" from the structure of an object that says in its own text it gates nothing. That's the least defensible foundation available to you, and you led with it.

Arguments 2 and 3 are the real ones and both hold up under measurement. Argument 3 especially: 397 `minimize` / 87 `maximize`, confirmed. "A way an artifact might break" is unfalsifiable-by-construction against *"maximize likelihood of a reproducible installed-substrate"* — 18% of the corpus is not a rounding error. Argument 2 holds: `planner.wmbt.shape` is `status: active` and glosses `proving_artifacts` as "the acceptances/tests that prove the WMBT statement."

**A better frame than "schema is authority":** the repo already ruled on this. Issue #760 hit the same conflict and resolved it the *other* way — it changed the **schema** to honestly describe the **corpus** (that's why `acceptances` and the `$comment` exist at all). The established precedence in this repo is corpus > schema > prose. That frame is stronger for you: it's why `statement`/`context_clarifier` belong in the prose despite not being `required` (484/484), and why `status`/`acceptance` must go (0/190). It also warns you that schema *silence* is not authority — which is exactly where question 3 goes wrong.

## 3. Feature — right to drop "feedback loop" and "size limits"?

**Right to drop `status` and `acceptance`. Wrong to drop "stays within its size limits." Wrong to delete "closes a feedback loop" — it needs conditionalizing, not removing.**

Both claims are expressed, and both are `status: active`:

- `planner.feature.size-max-rule` — *"features MUST be S or smaller, else split or stage before execution"*, `max_size: S`, `max_components: 8`, WMBT brackets XS≤5 / S 6-10 / M 11-20 / L >20.
- `planner.feature.hard-limits` — `kind: constraint`, ≤2 new tables, ≤2 async jobs, ≤2 integrations.
- `planner.feature.feedback-loop-close-the-loop` — `implementation: {type: validator, ref: planner.smoke.feedback-loop-close-the-loop}`. This is one of the few things in the feature family bound to an actual validator, and your replacement is the only one of the three that deletes a pointer to a bound rule.

And `sizing.footprint_size` is a schema field with enum `XS|S|M|L|XL`. So "stays within its size limits" isn't intent-the-schema-can't-encode — it's a norm *over* a field the schema does encode. `"states its sizing"` replaces a constraint with a shape declaration. That's not neutral, because the constraint is currently violated: **51 M + 9 L out of 190 features (31.6%) exceed `max_size: S`.** Retiring the only prose statement of a rule that 60 artifacts break, inside a PR framed as "correcting drift," is an editorial act that deserves its own line in the proposal rather than a silent omission.

On feedback-loop, you've misdiagnosed the defect. The rule is conditional — *"A feature marked `kind: feedback-loop` must declare at least one SMOKE acceptance with a `close_the_loop` block"* — and the definition asserts it of every feature. The error is **universalization of a conditional**, not unsupportedness. (Side finding you didn't catch: `kind` is not a property of `feature.schema.json` at all. An active validator keys on a field the schema never declares. Since root `additionalProperties` is absent this isn't invalid, but it's a genuine schema gap and arguably the most actionable thing in this whole audit.)

Suggested B:

> A feature is the smallest independently-verifiable slice of a wagon's behavior — a bounded capability that declares a `urn`, links to exactly one `wagon`, carries a `description`, declares the `wmbts` it covers, and enumerates its `components`; its `sizing` must stay within the feature size limits, and a feature marked `kind: feedback-loop` must close the loop it opens.

## 4. Is the acceptance sufficient, or theatre?

**Neither. It's too narrow to catch the drift you found, and your binary framing hides the option you should take.**

Three concrete failures of the proposed check:

**(a) It would fail on your own output — or be scoped so narrowly it catches nothing.** You rewrite `statement:` on all three nodes and leave `terms:` untouched. After your patch, `planner.feature.definition` still reads:

> `well-shaped: declares a urn, a status, and a non-empty acceptance section (see planner.feature.shape).`

and `planner.wmbt.definition` still reads:

> `well-shaped: declares its id, its statement, and the artifacts that prove the statement`

`id` is not a WMBT field. The schema has `urn`. So a check that reads the whole node fails on your fix; a check that reads only `statement:` misses two of the three drifts still sitting in the file. You must patch the `terms:` blocks too — that's a gap in the proposal, not just in the check.

**(b) It targets the draft node and leaves the active one wrong.** `planner.feature.shape` is `kind: rule`, `status: active`, and says verbatim: *"Feature YAMLs declare a urn, a status, and a non-empty acceptance section."* That is the **source** of the drift — the definition node's terms literally say "see planner.feature.shape". Your scope fixes the advisory copy and leaves the active original, and your acceptance is scoped to `*.definition` nodes so it can't ever see it. You're correcting the echo.

**(c) "its schema" isn't a well-defined mapping.** `planner.interlocking.definition` has two candidate schemas (`train-interlocking.schema.json`, `_dispatch.schema.json`) and the check's verdict flips depending on which you pick. `planner.theme.definition` has zero — you note this and leave the check's behavior on "no schema" unspecified (skip? fail? which?). `planner.artifact.definition` likewise. `planner.definition.anchor-required` mandates all seven anchors, so the check has to answer for all seven.

**The third option you didn't consider.** You frame it as bind-the-nodes (wrong approval path) vs. a new free-floating acceptance. But `planner.definition.anchor-required` already exists: `status: active`, `severity: 3`, `disposition: strict`, `implementation.ref: test_definition_anchors::test_every_core_artifact_has_definition_anchor`. There is already an active, strict, validator-bound rule *about the definition nodes*, and its validator already enumerates the seven. Extending that test with a content assertion needs no promotion of the family nodes, no new `binding.lock.yaml` entry, and no substrate approval path. That's strictly better than a new acceptance, and it closes your own objection.

So: the check isn't theatre, but as scoped it's aimed at the wrong nodes, and the existing anchor rule is the right place to put it.

---

## Two things in "mechanical corrections" that aren't mechanical

**`inventory.py` is a behavior change, not a docstring fix.** Your fix list says it "gets the right expansion and all nine step codes." But `by_category` emits keys `contract/logic/edge/performance` into `inventory["wmbt_acceptance"]["by_category"]` at line 682, and prints at 683. Correcting the taxonomy renames every key in a consumer-visible output dict and changes `total` 334 → 484 (+45%). The method name `scan_wmbt_acceptance` and the printed string "WMBT acceptance files" also repeat the exact noun error you're fixing elsewhere. Either rename them in the same PR or you've left the defect in the identifier while fixing it in the comment.

Your undercount is exact, confirmed: `{C:98, L:16, E:208, P:12} = 334`; actual `{E:208, C:98, D:74, Y:29, R:20, M:19, L:16, P:12, K:8} = 484`.

Note also that `issue.convention.yaml:601` **already** carries all nine codes correctly (`D=define, L=locate, P=prepare, C=confirm, E=execute, M=monitor, Y=modify, R=resolve, K=conclude`). The repo already contains the right answer; `inventory.py` just never read it.

**`label_taxonomy.schema.json:94` writes to GitHub.** That `description` const is consumed by `initializer.py:_create_labels`, which shells `gh label create … --description desc --force` against the real repo. Changing it changes a label description on GitHub on the next init/sync. It's idempotent and low-risk, but it's an outward-facing write, and it must move in lockstep with `issue.convention.yaml:197` (identical string) or the two sources diverge.

## Missed while you were in there

- `issue.convention.yaml:32,36,40` point at `atdd/planner/conventions/{wagon,feature,wmbt}.convention.yaml`. That directory has no `*.yaml` files — the nodes moved to `conventions/nodes/`. Three dead paths, same three lines you're already editing.
- Same block, line 39: WMBT `location: "plan/{wagon}/features/{feature}.yaml (wmbt section)"`. WMBTs live at `plan/{wagon}/E001.yaml`. Line 601 has it right (`plan/{wagon}/*.yaml`). A wrong location is a worse defect than a wrong noun, and it's one line above a line you're already touching.
- `kind` is used by an active feature validator and declared nowhere in `feature.schema.json`.

## What I'd ask you to change before merge

1. Fix the `additionalProperties` claim and rewrite argument 4 as *omits 4 of 6 required fields*.
2. Make C additive — keep artifact-keying, add guard/`route_resolution`; or split C out and land A/B first.
3. Patch `terms:` on all three nodes, and fix `planner.feature.shape` (active) in the same PR.
4. Keep "size limits" in B; conditionalize rather than delete the feedback-loop clause.
5. Move the check into `test_definition_anchors` and specify its behavior for `theme`/`artifact` (no schema) and `interlocking` (two schemas).
6. Reframe the authority argument on the #760 corpus-over-schema precedent; drop the nesting argument.

Two I'd accept as-is: leaving `theme` alone (no schema, not assessable — correct call), and treating "Way My Brain Tests" as a graphify artefact (confirmed: zero occurrences in tracked source).
