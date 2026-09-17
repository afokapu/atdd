# Review: ATDD #2039 definition-node corrections

I verified your claims against a full repo snapshot before reviewing (mine is marginally behind yours: 474 WMBTs / 188 features vs your 484/190 — proportions identical, and your inventory-miss breakdown reproduces **exactly**: D74 Y29 R20 M19 K8 = 150 missed). Your corpus measurements are solid. Your framing of *authority* is not. Two of your three corrections survive contact with the repo; one (B) I reject as written; and your proposed recurrence test would have caught **one of your three motivating defects**.

## The premise problem: "the schema is authority" is inverted for two of your three kinds

You did not cite `src/atdd/planner/commands/plan_unit_schema.py`, and it decides half your argument. Its docstring, with measurements:

> "Measured against this repo's own `plan/` tree, `feature.schema.json` **rejects 134 of 188 real features** and `wmbt.schema.json` **294 of 468 real WMBTs** — the latter says so in its own `$comment`. Raising on those would refuse the decomposition this repo ships, so they REPORT and the findings ride on the unit; the honest schemas RAISE."

The `SPEC_SCHEMAS` tier table: `wagon`, `train`, `interlocking`, `acceptance` are **enforce** (each validated 100% against the in-repo corpus); `feature` and `wmbt` are **advise**. And `wmbt.schema.json`'s own `$comment` states there is no `jsonschema.validate(wmbt_data, this_schema)` anywhere — the schema is a post-hoc description, and `additionalProperties: false` there "is never enforced against files."

So the authority hierarchy you're invoking holds for **interlocking** (replacement C is anchored to an enforce-tier, 100%-corpus-valid schema — good), but for **feature and wmbt** the schema is a known-broken mirror that the repo deliberately doesn't raise on. The working authorities there are the Python validators (`planner/validators/test_wmbt_vocabulary.py` enforces step/direction/dimension/lens vocabularies *and* the statement pattern) plus the corpus. Your replacements A and B happen to agree with the validators too — but your argument should say so, because a future contributor who takes "schema is authority" literally will align definitions to a schema that rejects 71% of real feature files.

Two corrections to your evidence table while I'm here:

- **"feature.schema.json properties (additionalProperties-constrained)" is false at the level that matters.** The top level has *no* `additionalProperties: false` (I checked programmatically; only sub-objects like `sizing` and `components` carry it). Consequently your claim that the feature definition "instructs authors to produce an invalid artifact" is wrong in the strict sense: a feature with `status:` and `acceptance:` keys would *pass* the schema. The real defect is corpus-inconsistency (0/188, confirmed) — documentation describing a shape nothing produces and nothing rejects. That distinction matters for Q4, because it means there is currently no gate at all on the B-class defect, on either side.
- **"the sibling node `planner.wmbt.shape` is already correct"** — it says a WMBT "declares its **id**." There is no `id` field; it's `urn`. That's the same defect class you're hunting, one hop away. Ninety percent correct is not "correct" in a proposal about definitional drift.

---

## Q1. Is "measurable outcome" the right head-noun?

**Close, but no — you've swapped one category slip for another.** The drifted text called a WMBT a *risk* ("a way an artifact might break"); your replacement calls it *the outcome itself*. A WMBT is neither: it is a **statement** — a declarative assertion of an outcome. Your own authority says so: the schema's description is "Schema for What Must Be True **statements** that define measurable outcomes," and the artifact carries a `statement` field that `test_wmbt_vocabulary.py` parses against the composition pattern. A thing with a subject-predicate text, a URN, and a proof tier is an assertion, not a state of the world. "A WMBT … is a single measurable outcome that must hold" is exactly as ontologically confused as "a feature spec is a working feature."

Recommended head: **"A WMBT (What Must Be True) is a measurable, directional statement — a declaration of one outcome that must hold for a wagon's job to be done…"** The schema's own field prose supports the outcome *referent* ("where in the job flow this outcome matters," "how to improve the outcome") while keeping the artifact a statement.

Credit where due, on two claims you made without citing their backing:

- Your grammar claim — "`statement` is composed as `{direction} {dimension} of {object_of_control} [context_clarifier]`" — is **enforced**, not just schema-described: `planner.wmbt.statement-template.convention.yaml` (kind: rule, status: active) states that exact template, and the vocabulary validator checks it. Cite those; they're stronger than the schema's `description` string.
- "qualified by a `context_clarifier`" — the field is *optional* in the schema, but present in 474/474 corpus files, so the phrasing survives empirically. I'd still write "optionally qualified" for honesty, since nothing enforces presence.

Your dropped "falsifiable" was doing real work tied to the break-framing; under outcome-framing the acceptances do the falsifying, and your final sentence already says so. Good.

## Q2. Is the structural argument sound?

**The conclusion is sound; the nesting premise is your weakest leg, and you should stop leading with it.** JSON-Schema nesting alone proves nothing — schemas routinely nest same-kind things (rules under rules, criteria under criteria). What actually settles it, all verified:

1. **The three-tier structure, measured.** Features carry `wmbts` as URN arrays (188/188) and `acceptance` 0/188 — features never carry acceptances. Acceptances attach *to WMBTs*, embedded (see any `plan/<wagon>/E###.yaml`). A two-level model would have features carrying criteria directly. It's `feature → wmbts → acceptances`, not `feature → criteria`.
2. **The active shape rule.** `planner.wmbt.shape`: proving_artifacts = "the acceptances/tests that prove the WMBT statement." Prove-er vs. prove-ee, stated in a bound-by-validator rule.
3. **Recursion absurdity.** `planner.wmbt.must-have-smoke-acceptance` requires every WMBT to *declare* at least one SMOKE acceptance URN. A criterion that must itself carry criteria is a category confusion the rule grammar can't express.
4. **Disjoint grammars.** `acceptance.schema.json` is titled "Validates **acceptance criteria** in WMBT files" — acceptances (harness, phase, given/when/then) *are* the repo's acceptance criteria. WMBTs have direction/dimension/lens. Different tiers, different vocabulary — which is precisely why calling a WMBT "an acceptance criterion" in the coach sites erases the two-tier design.

So: not over-reading, but over-*crediting* the wrong evidence. Rewrite the argument on 1+4.

One caution on the mechanical corrections: `issue.convention.yaml:38` is not just a wrong noun — the same `wmbt:` block's `location:` says `"plan/{wagon}/features/{feature}.yaml (wmbt section)"`, contradicting both the corpus (standalone `plan/<wagon>/<STEP>NNN.yaml` files) and line 601's own artifacts glob `plan/{wagon}/*.yaml`. If you fix the noun and leave the location, you've re-labeled a wrong map. Fix the block, not the word.

## Q3. Dropping "closes a feedback loop" and "stays within its size limits"

**Split decision — you're right on the first, wrong on the second, and your general principle is over-applied.**

**"Closes a feedback loop": drop it — but for a stronger reason than yours.** It's not merely "a claim the schema does not express as a field." The referenced rules (`planner.feature.feedback-loop-close-the-loop`, `planner.smoke.feedback-loop-close-the-loop`) are *conditional*: "A feature **marked `kind: feedback-loop`** must declare at least one SMOKE acceptance with a close_the_loop block…" — i.e., they key on a `kind:` field that appears in **0/188** feature files and exists nowhere in the schema, and they require SMOKE acceptances *on the feature*, which is doubly nonexistent. The definition's unconditional "closes a feedback loop" overstates a dormant conditional rule family. (The validator `planner/validators/_feedback_loop.py` is live code, born of the 2026-05-21 incident — dormant, not dead. Leave it; just stop letting the definition assert its condition as universal.)

**"Stays within its size limits": keep it. You are deleting the anchor's reason to exist.** The definition node's own architecture — which you preserved in your replacements — says "the enforceable parts of this meaning are decomposed into the constraint/rule nodes that require it." Those nodes exist and are active: `planner.feature.size-max-rule` ("features MUST be S or smaller, else split or stage"; brackets XS≤5 … L>20) and `planner.feature.hard-limits` (2 tables / 2 async jobs / 2 integrations). And the schema *does* express size as fields — `sizing.footprint_size` (enum XS–XL) and `sizing.wmbts` — so this isn't even a "field the schema does not declare." Your replacement "states its `sizing`" keeps the noun and deletes the norm: a definition that mentions sizing while omitting that S is the ceiling documents a form with the rule amputated. Restore it, ideally as "stays within its size limits (see `planner.feature.hard-limits`, `planner.feature.size-max-rule`)."

The deeper problem with B: **your anti-drift principle is valid as a negative test and invalid as a rewrite rule.** "Don't name fields the schema doesn't declare" — yes. But applying the inverse ("the definition should only assert what the schema encodes") produces a prose mirror of `required:` — and for feature that schema is advise-tier and rejects 134/188 real files. A definition that merely restates field lists is (a) redundant with the schema, (b) a fresh drift surface the moment the schema evolves, and (c) stripped of the intent an "advisory semantic anchor" exists to carry. Definition = what the artifact is *for*, its key structure, and its limits — minus false field claims. Your B is the weakest of the three replacements.

**Also: B as scoped is cosmetic, because you're fixing one of three sites carrying the same lie.** `planner.feature.shape` — kind: **rule**, status: **active** — states "Feature YAMLs declare a urn, **a status, and a non-empty acceptance section**," and the definition node's own `terms:` block (`well-shaped`) repeats it verbatim. Your proposal replaces the definition's `statement:` and walks past an active rule node and the terms block. Same defect, same evidence, one hop away. If the proposal's title says "correcting three drifted convention nodes," this is a fourth.

## Q4. Is the acceptance sufficient, or theatre without binding?

**Binding is the wrong tool and declining it is correct — but not for your reason, and your test as specified is misaimed.**

On binding: `binding.lock.yaml` contains **zero** `planner.*` entries. No planner convention — definition or otherwise — has ever been lock-bound; the planner family's entire enforcement mechanism is the pytest validator suite. `test_definition_anchors.py` already proves the pattern: it binds `planner.definition.anchor-required` and enforces structural properties of these very definition nodes (kind: family, graph-connected) via `bind_rule` + `assert_disposition_satisfied`. Your acceptance would be the second validator in an established family, not a novelty. So "promoting them to bound rules is a substrate act" is true but understated — it would make them the *first* bound planner conventions. Right call. Your worry "is that too weak?" has the wrong target: the mechanism is fine; **the check is weak**:

1. **It would not have caught your own motivating defects A and C.** "Definition node names no field absent from its schema" is a lexical negative test. "What-Might-Break Test" names no field. Interlocking's "keyed by a produced artifact (the divergence signal)" names no absent field — it's a semantic misdescription (the enforce-tier schema keys routes by guards + `route_resolution.strategy`, not artifact URNs). Your test ratchets exactly the B-class — the *easiest* class — and leaves A-class (wrong meaning) and C-class (wrong mechanics) untouched. Design it backwards from "would this have failed on all three defects as found?"
2. **It's keyed to the wrong authority for feature/wmbt** — advise-tier schemas the repo documents as rejecting most real files (see premise section). The check should read: enforce-tier schema where the kind has one (wagon/train/interlocking/acceptance); otherwise the validator vocabularies (`AUTHORIZED_STEPS`, `AUTHORIZED_DIRECTIONS`, …) and the corpus field union.
3. **It reads only `statement:`.** The terms blocks carry field claims — WMBT's says "declares its **id**," feature's carries the status/acceptance claim via `well-shaped`. Drift survives your test in `terms:`.
4. **Theme's exemption is factually wrong.** "No `theme.schema.json` exists, so not assessable" — but `planner/validators/_theme_taxonomy.py` owns the digit→theme map, digits 0–4, digit-0 locked to commons (operator decision #970). No JSON Schema ≠ no authority; the taxonomy validator is the analog, and it confirms the theme definition as written. Cover it.
5. **Two cheap checks would catch the classes your test misses:** (a) *acronym canon* — a single tracked-source expansion of "WMBT" == "What Must Be True" (you already grepped three variants; it's a five-line test, and it catches A-class); (b) *inventory coverage* — coach inventory's recognized step codes ≡ the nine validator codes with matching meanings (catches the `inventory.py` class — your hand-fix repairs 150 missing WMBTs but, as scoped, installs no regression guard, so the next step letter that gains files silently re-drifts).

Minimum bar for "sufficient": it should have failed on all three defects as found. As specified, it fails that bar. With the above amendments it passes it, without binding anything.

---

## Scope decisions, challenged

- **Not binding the definition nodes — agree**, but restate the reason: zero planner lock entries; validators are the planner family's enforcement mechanism, and `test_definition_anchors.py` is the precedent.
- **Leaving wagon/train/artifact alone — verified correct.** I read all three; they're consistent with their enforce-tier schemas and child rules.
- **Theme — wrong reasoning, right outcome** (see Q4.4).
- **"Way My Brain Tests" as graphify artefact — consistent with my snapshot** (zero occurrences in tracked source).
- **Missed scope:** (1) `planner.feature.shape` — same status/acceptance drift in an *active* rule node; (2) `issue.convention.yaml:38`'s `location:` field, contradicted by the corpus and by line 601 in the same file; (3) no regression test for the inventory fix. And in `inventory.py`, make the pattern map *read* `planner.wmbt.step-code-vocabulary` (or the validator's `AUTHORIZED_STEPS`) rather than duplicating the nine meanings — a duplicated list is next quarter's drift.

## Verdict

A: fix the head-noun to "statement," cite the statement-template rule and vocabulary validator as your authority, and it ships. B: reject as written — restore the size-limit clause, fix `planner.feature.shape` and the terms block in the same stroke, and anchor to corpus+validators, not the advise-tier schema. C: correct and properly anchored (enforce-tier schema; `route_resolution.strategy`, guards, and category all verified) — but fix the terms block's "artifact-keyed" value too, or your new statement contradicts your own node. Q4 mechanism: right (validators, not binding); check: too weak as specified — it should be designed to have caught all three of the defects that motivated it, and today it catches one.
