# #1714 slice 1 — the classification gate over the core coder/tester rule surface

**Measured:** 2026-09-13, on `feat/coder-agnostic-mirror-completion` at `origin/main`
with an empty diff (`git rev-list --left-right --count origin/main...HEAD` → `0 0`).

Reproduce every figure below with:

```
python3 tools/mirror-coverage/coverage.py
python3 tools/mirror-coverage/coverage.py --classification docs/1714-agnostic-mirror-coverage.md
```

This is the **no-silent-drop record** #1714's Validation section names and #1993 declares
it "consumes rather than performs". It is not an authoring record: no convention node is
written here, per #1714's Decision "Classify before authoring."

## Method

Every number is read through the shipped loader, never a hand-rolled YAML reader.

| Surface | Read by | Why not something else |
|---|---|---|
| core coder/tester rule_ids | `atdd.coach.utils.rule_binding.extract_rules` | walks nested `rules:` lists. `canonical_rules.rules[]` in `coder/conventions/logging.convention.yaml` is invisible to a depth-1 reader — the omission that understated the corpus in #1969, and the reason `.carve-lab/inventory.py` must not be used |
| twin provenance | `atdd.enforce.registry.iter_extension_nodes` | reads `source.legacy_rule_id` off the raw node document |
| mirror coherence | `atdd.enforce.registry.find_mirror_incoherences` | the shipped coherence rule |

**`extract_rules` cannot carry provenance.** `single_node_rule_dict`
(`src/atdd/coach/utils/rule_binding.py:261`) projects a single-node convention document
onto the flat monolith rule shape and keeps ten keys — `id`, `severity`, `description`,
`disposition`, `introduced_in`, `suppression_deadline`, `aliases`, `validator`,
`fix_hint`, `superseded_by`. `source` is not among them. Provenance keyed off
`extract_rules` output therefore reads as **absent on all 67** extension nodes, not
present on 50. Measured both ways:

| Keying | Twins found | Twinless |
|---|---|---|
| `source.legacy_rule_id` via `iter_extension_nodes` (raw document) | 32 | **96** |
| own-`rule_id` collision via `extract_rules` | 32 | **96** |
| `source.legacy_rule_id` via `extract_rules` output | 0 | 128 |

The first two partitions are **identical** — the same 32 rule_ids, so the figure does not
depend on which of the two valid keyings is used. The third is an artefact of the dropped
key. This is a live trap for #1973, whose GREEN phase places a provenance filter in
`src/atdd/coach/utils/rule_binding.py`: a filter reading `rule["source"]` there sees no
mirrors, admits all 67 nodes, and reintroduces exactly the 32 `AmbiguousRuleError`
collisions it exists to prevent. It must read the raw document, or reuse
`iter_extension_nodes`.

## The figure

```
core coder/tester rule_ids          : 128
  TWINNED (an extension mirrors it) : 32
  TWINLESS (no mirror at all)       : 96
    of those, why-not classified    : 7
    UNCOVERED (silent-drop risk)    : 89

extension nodes under .atdd/        : 67
  declaring source.legacy_rule_id   : 50
  mirror-coherence failures         : 35
```

**96 of core's 128 coder/tester rule_ids have no extension twin at all** — reproduced.
Consistent with #1973's corpus (163 ids across both surfaces, 67 extension, 32 in both)
and with #1993's Root Cause table (128 / 32 / 96 / 2 refused / 126 permitted).

## Why coverage is the only thing standing between #1993 and 96 lost obligations

`evaluate_core_deletion` (`src/atdd/enforce/registry.py:351`) opens:

```python
node_twins = twins.get(rid) or []
if not node_twins:
    continue  # no mirror → no twin enforcement to lose
```

A **twinless** core rule is the one whose obligation exists in core and nowhere else, so
deleting it is maximal loss — and it is waved through, while a twinned-but-advisory rule
is refused. The guard's premise is inverted with respect to a carve-out program. Over
this tree that branch permits all 96.

The hole is not only a code branch: it is a **declared planner acceptance**.
`acc:guard-succession:E003-UNIT-002` (`plan/guard_succession/E003.yaml`) asserts
"deleting the rule that no extension node mirrors is permitted (no twin enforcement to
lose)", and `test_e003_unit_002_safe_succession_and_untwinned_deletion_allowed.py` pins
it. Closing the hole (#1993 Phase 1/2) therefore requires amending that WMBT's
acceptance, not only the branch — otherwise the RED test contradicts a live acceptance.

Once coverage reaches 128/128 the branch never fires, and the guard falls through to its
bound-AND-blocking test. Coverage is the mechanism that closes it; #1993's guard change
is what makes the closure loud rather than silent.

## Corrections to the briefs

| # | Brief says | Measured | Consequence |
|---|---|---|---|
| 1 | #1714 cites `official/atdd.extension.coder/conventions/` | the package is `official/atdd.extension.coder.base` (`atdd-extensions@main`), installed at `.atdd/extensions/atdd.extension.coder.base/0.1.0/` | #1714's headline command returns **0** and reads as an empty mirror. The real count is **48** nodes, which is the baseline #1714's Context table already states |
| 2 | #1714 declares `train:govern-lifecycle:enforcement-substrate` / `feature:govern-lifecycle:coder-extension-conventions` | neither exists. `govern-lifecycle` appears in `plan/_wagons.yaml` as a **wagon**; no train namespace of that name exists in `plan/_trains.yaml` | #1714 cannot reach PLANNED, and so cannot legally reach RED, until planner artifacts exist. A RED test written now would carry no acceptance URN — an ad-hoc test, forbidden by gate constraint 1 |
| 3 | #1714's Artifacts are all `official/…` and `docs/agnostic-classification/…` | those are `atdd-extensions` paths; `atdd-extensions` has no `plan/` tree | #1714 spans two repos: the nodes land in `atdd-extensions`, the coverage gate must live in core, because it reads core's registry |

## Reconciled: the 35 mirror incoherences, and why none of them is drift

`test_e001_smoke_001_real_mirrors_all_resolve_to_live_core_rules.py` **fails on
`origin/main`** with 35 incoherences. Not introduced by this branch (empty diff).

`find_mirror_incoherences` treats a node whose `legacy_rule_id` names no live core rule —
including a node with no `legacy_rule_id` at all — as a drifted mirror. That encodes
#1427's premise that *every* extension node mirrors a core rule.

**Adjudicated, all 35. None is a drifted mirror.**

| Group | Count | Verdict | Evidence |
|---|---|---|---|
| `atdd.extension.coder.base` | 18 | **COMPLETED CARVE-OUT** | every one of the 18 legacy ids was removed from core by a single commit, `47c4d414` (#1518, 2026-07-18), whose message hands them to this extension by name: "18 TS rule blocks (complexity-\*-typescript, quality-\*-typescript, no-intra-layer-code-typescript, dead-code-typescript, design-system, gsap, i18n) -> atdd.extension.coder (strict) and vite-coder". 18 of 18 matched, **0 unexplained** |
| `atdd.extension.{coder,tester}.train-interlocking` | 17 | **EXTENSION-NATIVE** | no `legacy_rule_id` at all: they claim no core ancestor because they never had one |

So the legacy id naming no live core rule is, for all 35, the **correct end state** — in
the first group because the succession already happened, in the second because there was
never anything to succeed. The reading that these are "extension-native obligations
wearing mirror provenance" was wrong: the provenance is accurate and the rule it names is
gone on purpose.

### The defect this exposes, which does block #1714 and #1993

`find_mirror_incoherences` cannot tell three states apart, and reports the two legitimate
ones as the fault:

| State | `legacy_rule_id` | Correct verdict | Reported today |
|---|---|---|---|
| stale mirror — the core rule was **renamed** | names a dead id | FAIL (this is drift) | FAIL |
| completed carve-out — the core rule was **deliberately deleted**, this node superseded it | names a dead id | pass | FAIL |
| extension-native obligation | absent | pass | FAIL |

The two signals are identical in the data, so no widening of the rule can separate them
from the node alone: a **retirement must be declared**, the same conclusion #1993 reaches
for `evaluate_core_deletion`'s twinless branch. Both guards need the same missing fact.

**Built — `wmbt:govern-registry:E004`.** `.atdd/retirements.yaml` declares the 18, read
by `atdd.enforce.retirements`, honoured by `find_mirror_incoherences(..., retirements=)`.
Real findings **35 → 17**, and every one of the 17 has `legacy_rule_id: None` — so the
residual is the third state, not a smaller pile of the second. An absent ledger retires
nothing and an entry with no `retired_in` is refused, so a rule is forgiven only by an
explicit, evidence-bearing declaration. #1993 consumes the same reader for its guard
rather than growing a second one.

This is load-bearing for the program, not cosmetic. #1714 authors 89 new agnostic nodes
and #1993 then deletes core's copies — which manufactures state 2 eighty-nine times over.
Left as is, the gate goes from 35 red to roughly 124 red and can never return to green,
so #1714's SMOKE exit condition is unreachable by construction. Its own output is
individually fine — a node mirroring one of the 89 names a live core rule while core still
holds it — but the moment #1993 moves that rule, the node becomes an "incoherence".

Also measured: of `coder.base`'s 48 nodes only **30** mirror a live core rule (the other 2
of the 32 twins are tester), so the mirror baseline is 30, not 48.

## Classification — 20 of 128 rules adjudicated, 9 queued to mirror

Vocabulary and method are `docs/MIRROR-GAP-ASSIGNMENT.md`'s SHARED METHOD
(`atdd-extensions@main`), reused verbatim: **AGNOSTIC-CONSUMER → mirror** vs
**ATDD-INTERNAL / SUBSTRATE-SPEC → why-not with quoted evidence**.

### ATDD-INTERNAL — `coder.state-store` (7 rules)

Verdict confirmed, not assumed: every statement names ATDD's own substrate modules and
artifacts, so none states an obligation on consumer code. #1714 declares this family Out
of Scope on a provisional ATDD-INTERNAL verdict; this is the evidence that settles it.

| rule_id | verdict | disposition | Quoted evidence from its own `statement` |
|---|---|---|---|
| `coder.state-store.core-imports-no-providers` | ATDD-INTERNAL | strict | "The State Store (`atdd.state`) is a foundational layer and must not import the upper layers `atdd.coach`, `atdd.train`, `atdd.integrations`, or `atdd.runtime`." |
| `coder.state-store.no-raw-sql-at-call-sites` | ATDD-INTERNAL | strict | "Outside the State Store package (`atdd.state`), no module may import `sqlite3` directly." |
| `coder.state-store.one-external-ref-per-issue` | ATDD-INTERNAL | strict | "the `external_refs` schema enforces this structurally with `UNIQUE (provider, ref_kind, ref_value)` … the import-collision rule that manifest import relies on" |
| `coder.state-store.operational-vs-definition-sot` | ATDD-INTERNAL | strict | "OPERATIONAL / instance state (work-items, version, runs, sessions) is owned by the State Store (`atdd.state`) as SoT" |
| `coder.state-store.single-store-per-control-root` | ATDD-INTERNAL | strict | "no child git worktree may carry its own `.atdd/state/state.sqlite` … The `check_layout` guard implements this rule and must be wired into the state CLI" |
| `coder.state-store.sync-engine-provider-agnostic` | ATDD-INTERNAL | strict | "The State Store sync engine (`src/atdd/state/sync_engine.py`) must name no concrete provider" |
| `coder.state-store.work-item-provenance` | ATDD-INTERNAL | advisory | "Every `work_item` in the State Store has a sanctioned authoring event as its first event." |

**No mirror is built for these 7.** They are covered by this record, not by a node — which
is exactly the disjunction the no-silent-drop guard tests.

### SUBSTRATE-SPEC — the ATDD substrate's own format (11 rules)

These govern the shape of ATDD's own artifacts — `plan/` acceptances, `plan/_trains.yaml`,
`e2e/<train_id>/`, the composed convention graph. A consumer repo has those artifacts, so
the rules reach consumers; but the artifact is the same in every language, the detector is
the same in every language, and there is no per-stack realization to delegate. An agnostic
node with a per-stack detector is the wrong shape for them: they belong to the substrate
spec, and core is where the substrate spec lives.

The evidence is the scan surface, read from the validator each node binds.

| rule_id | verdict | disposition | Quoted evidence |
|---|---|---|---|
| `tester.acceptance-violation.acceptance-must-be-measurable` | SUBSTRATE-SPEC | strict | bound to `_acceptance_walker`, whose purpose line reads "Shared helper for substrate enforcement validators (#410) — walks `plan/` for raw acceptance blocks"; the rule is "Every acceptance in `plan/` must declare harness.type … or signal.metric + signal.threshold" |
| `tester.acceptance-violation.acceptance-must-declare-phase` | SUBSTRATE-SPEC | strict | "Every acceptance in `plan/` must declare `identity.phase` explicitly" — a field of ATDD's acceptance schema |
| `tester.acceptance-violation.disposition-must-not-be-declared` | SUBSTRATE-SPEC | strict | "Repo acceptance and security YAML must NOT declare a `disposition:` field — the substrate sets it to strict for all repo rules" |
| `tester.acceptance-violation.hermetic-fake-must-declare-contract` | SUBSTRATE-SPEC | strict | "must declare its hermetic fidelity contract (`exercised_boundaries`, `fake_contract_fidelity` with `known_gaps`, `live_smoke_required`) using only controlled boundary" vocabulary — ATDD's acceptance vocabulary |
| `tester.acceptance-violation.hermetic-live-smoke-required-must-have-paired-smoke-acceptance` | SUBSTRATE-SPEC | strict | "must have a sibling `execution_kind: live_smoke` acceptance under the same parent WMBT" — a relation between two plan/ blocks |
| `tester.acceptance-violation.security-rule-must-have-acceptance-ref-resolved` | SUBSTRATE-SPEC | strict | "Every `abuse_case` in `feature.yaml::security.abuse_cases[]` must have `acceptance_ref` pointing at a real acceptance" |
| `tester.acceptance-violation.validator-binding-must-be-bidirectional` | SUBSTRATE-SPEC | strict | "When `harness.type` is declared, an anchored test must exist whose headers match the acceptance" — the `# URN:` / `# Acceptance:` header block is ATDD's own |
| `tester.smoke.train-chain-complete-from-red` | SUBSTRATE-SPEC | strict | "Every train whose owning issue has reached RED must carry the full chain of E2E plus smoke coverage" — keyed on ATDD's train and issue phase |
| `tester.smoke.train-e2e-required-from-red` | SUBSTRATE-SPEC | strict | "must have E2E tests under `e2e/<train_id>/`" — ATDD's prescribed layout |
| `tester.smoke.train-smoke-required-from-red` | SUBSTRATE-SPEC | strict | its validator resolves `"plan/_trains.yaml:{s.train_id}"`, `"e2e"`, `"plan"` |
| `tester.test-isolation.no-polluting-patterns` | SUBSTRATE-SPEC | strict | it is a convention-graph policy variant: "Instantiates the `policy/forbidden_construct_absence` template against the composed convention graph", SELECTOR "graph nodes/artifacts matched by a policy scope" — it scans the convention graph, not consumer source |

### ATDD-INTERNAL — the train runtime (2 rules)

| rule_id | verdict | disposition | Quoted evidence |
|---|---|---|---|
| `coder.train.acceptance-commit-idempotent` | ATDD-INTERNAL | unset | "An **Acceptance Authority** commit MUST be idempotent — the same `idempotency_key` returns the original receipt … a receipt is recoverable across the commit/receive" — ATDD's own acceptance-commit runtime; binds no validator (`implementation.ref` is absent) |
| `coder.train.station-master-owns-child-train-fanout` | ATDD-INTERNAL | unset | "fan-out is owned by the **Station Master** … suspend/resume state lives in the durable **run-log**, not in TrainRunner" — ATDD's interlocking runtime; binds no validator |

### AGNOSTIC-CONSUMER — mirror these 9

The other half of the enforcing batch. Each states an obligation on the consumer's own
code and already has a stack-specific realization, which is exactly the agnostic-parent /
per-stack-detector shape. These are the highest-value nodes to author first: the detector
exists, so mirroring buys coverage **and** enforceability without inventing one.

| rule_id | disposition | Why it needs a per-stack realization |
|---|---|---|
| `coder.lint.ruff-ratchet` | strict | ruff is Python's linter; its own docstring says "consumer's `atdd validate coder` deselects it and never runs ruff". The obligation — no lint finding absent from the frozen baseline — is agnostic; eslint / dart analyze realize it elsewhere |
| `coder.types.pyright-ratchet` | strict | same shape, pyright; "consumer's `atdd validate coder` deselects it and never runs pyright" |
| `coder.coverage.every-feature-must-have` | strict | `test_hierarchy_coverage` resolves implementation roots "from `.atdd/config.yaml` `code:` block … so new stacks can be added per-consumer without forking" — explicitly stack-extensible over consumer code |
| `coder.coverage.every-implementation-must-have` | strict | same validator, same stack-extensible code roots |
| `tester.coverage.tracking-manifest-must-be` | strict | same validator family |
| `tester.smoke.no-collaborator-substitution` | suppress-and-clean | declares its own scope: "**Scope (Tier 1): Python only.** Backend smoke tests" — a stack-scoped realization whose agnostic parent is missing |
| `tester.acceptance-violation.live-smoke-acceptance-must-execute` | strict | the subject is a plan/ acceptance but the detection is Python: it matches `pytest.skip(...)`, `pytest.importorskip(...)` in harness source |
| `tester.acceptance-violation.live-smoke-evidence-must-not-be-constant` | strict | AST-walks the harness function for a constant-only return — Python-specific detection of an agnostic obligation |
| `tester.acceptance-violation.metric-implementation-must-exist` | strict | looks for `compute()` in `<repo>/.atdd/metrics/<metric>.py` — the `.py` is the stack. Classified AGNOSTIC on the conservative reading: a why-not row means no mirror is ever built, so ambiguity resolves toward mirroring |

### The remaining 26 families — 76 rules, unclassified

Each row is one worker's end-to-end unit per #1714's "Family-sized workers" decision.
`kinds` distinguishes an already-atomized core node from a rule still inside a monolith
(a monolith rule cannot carry per-rule provenance, so it waits on #1218).

| family | rules | kinds | dispositions |
|---|---|---|---|
| `coder.green` | 10 | monolith=10 | documentation-only=10 |
| `tester.smoke` | 7 | monolith=3, node=4 | documentation-only=6, suppress-and-clean=1 |
| `coder.commons` | 5 | monolith=3, node=2 | documentation-only=5 |
| `coder.design` | 5 | monolith=2, node=3 | advisory=1, documentation-only=4 |
| `tester.contract` | 5 | node=5 | documentation-only=5 |
| `tester.red` | 5 | monolith=1, node=4 | documentation-only=5 |
| `tester.coverage` | 4 | node=4 | documentation-only=3, strict=1 |
| `coder.backend` | 3 | monolith=1, node=2 | documentation-only=3 |
| `coder.dto` | 3 | node=3 | documentation-only=3 |
| `coder.presentation` | 3 | node=3 | documentation-only=3 |
| `coder.technology` | 3 | node=3 | documentation-only=3 |
| `tester.acceptance-violation` | 3 | node=3 | strict=3 |
| `coder.composition` | 2 | node=2 | documentation-only=2 |
| `coder.coverage` | 2 | node=2 | strict=2 |
| `coder.logging` | 2 | monolith=2 | documentation-only=2 |
| `tester.filename` | 2 | node=2 | documentation-only=2 |
| `tester.routing` | 2 | monolith=1, node=1 | documentation-only=2 |
| `tester.security` | 2 | node=2 | documentation-only=2 |
| `coder.boundaries` | 1 | node=1 | documentation-only=1 |
| `coder.duplication` | 1 | node=1 | documentation-only=1 |
| `coder.lint` | 1 | node=1 | strict=1 |
| `coder.security` | 1 | node=1 | documentation-only=1 |
| `coder.train` | 1 | node=1 | documentation-only=1 |
| `coder.types` | 1 | node=1 | strict=1 |
| `tester.telemetry` | 1 | node=1 | documentation-only=1 |
| `tester.train` | 1 | node=1 | documentation-only=1 |

Two observations for the herd:

- **66 of the 76 are `documentation-only`, and 23 of the 76 are monolith-declared
  (blocked on #1218, so only 53 are authorable today).** #1714's "Enforceable over documentation-only"
  decision applies to nearly the whole payload: each worker must decide whether a
  locatable per-file violation exists, and reach for `strict`/`advisory` with a detector
  when it does.
- **`coder.design` and `coder.presentation` need no reconciliation — author them
  normally.** An earlier draft of this record warned that these two families already have
  extension nodes (7 and 4 of the 18 above) and that authoring would duplicate an existing
  obligation. **That was wrong, and following it would have wasted the work.** The 11
  extension nodes are #1518's completed carve-out of the *TypeScript/design-system* rules
  (`token-color`, `orphan-export`, `gsap-layer`, `i18n-config`, …). The 8 core survivors
  are the *architectural layering* rules #1518 deliberately kept
  (`wagons-import-from-design`, `tokens-are-pure-values`, `layer-is-thin`,
  `controllers-never-call-domain`, …). The id sets are disjoint, no survivor is touched by
  #1518, and no survivor is mirrored by any extension node — they are different
  obligations that share a family prefix. Do not repoint any of the 11 `legacy_rule_id`s
  at a survivor: that would falsely mark a survivor twinned and drop a real obligation out
  of the shortfall.

## Next, in lifecycle order

1. ~~Adjudicate the 35 incoherences.~~ ~~Teach mirror coherence to accept a declared
   retirement.~~ **Both done** — 0 drift, and E004's ledger closes the growing half
   (35 → 17). What is left of this is the **17 extension-native nodes**: they declare no
   `legacy_rule_id` because they never had a core ancestor, and E001's premise still
   reads that as drift. Unlike the carve-out state, this set does **not grow** with the
   program, so it is a cheap follow-up, not a blocker — declare `origin: extension-native`
   on those nodes in `atdd-extensions`, or revise E001's premise. `test_e001_smoke_001`
   stays red until one of those happens.
2. ~~Create the planner artifacts #1714 names.~~ **Done** — re-homed onto
   `wmbt:govern-registry:E003` (the wagon already governs this relation; the train and
   feature #1714 names do not exist — correction 2). RED and GREEN landed:
   `atdd.enforce.twin_coverage` is the pinned measure.
3. **Author the 9 AGNOSTIC-CONSUMER nodes above.** Each already has a stack-specific
   detector, so mirroring buys coverage *and* enforceability with no detector invented —
   the best value per unit of work left in the program.
4. Then classify the 66 documentation-only rules before authoring any of them. 26
   families, 76 rules, of which only 53 are authorable today (23 are monolith-declared
   and wait on #1218). Classification has so far removed 20 rules from the payload for
   the cost of reading their statements — keep spending there before spending on nodes.
4. Coverage 128/128 → `coverage.py` exits 0 → #1993's precondition is met.
