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

## Pre-existing red gate: 35 mirror incoherences

`test_e001_smoke_001_real_mirrors_all_resolve_to_live_core_rules.py` **fails on
`origin/main`** with 35 incoherences. Not introduced by this branch (empty diff).

`find_mirror_incoherences` treats a node whose `legacy_rule_id` names no live core rule —
including a node with no `legacy_rule_id` at all — as a drifted mirror. That encodes
#1427's premise that *every* extension node mirrors a core rule. Two groups break it:

| Group | Count | Shape |
|---|---|---|
| `atdd.extension.coder.base` | 18 | `legacy_rule_id` **equals the node's own `rule_id`**, and that id is not in core — `coder.design.*` (7), `coder.presentation.*` (4), and 7 `*-typescript` stack variants. These are extension-native obligations wearing mirror provenance, not mirrors |
| `atdd.extension.{coder,tester}.train-interlocking` | 17 | no `legacy_rule_id` at all — genuinely new obligations, correctly having no core ancestor |

So of `coder.base`'s 48 nodes only **30** mirror a live core rule (the other 2 of the 32
twins are tester). This matters for #1714 in two ways: the mirror baseline is 30, not 48;
and the gate as written cannot express "a new agnostic obligation", which is what #1714
authors. #1714's own output is safe — a node mirroring one of the 96 declares a
`legacy_rule_id` that *is* live, so it is coherent — but the gate is red before the
program starts and stays red unless the 35 are adjudicated.

## Classification — 1 of 28 families settled

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

### The remaining 27 families — 89 rules, unclassified

Each row is one worker's end-to-end unit per #1714's "Family-sized workers" decision.
`kinds` distinguishes an already-atomized core node from a rule still inside a monolith
(a monolith rule cannot carry per-rule provenance, so it waits on #1218).

| family | rules | kinds | dispositions |
|---|---|---|---|
| `coder.green` | 10 | monolith=10 | documentation-only=10 |
| `tester.acceptance-violation` | 10 | node=10 | strict=10 |
| `tester.smoke` | 10 | monolith=3, node=7 | documentation-only=6, strict=3, suppress-and-clean=1 |
| `coder.commons` | 5 | monolith=3, node=2 | documentation-only=5 |
| `coder.design` | 5 | monolith=2, node=3 | advisory=1, documentation-only=4 |
| `tester.contract` | 5 | node=5 | documentation-only=5 |
| `tester.red` | 5 | monolith=1, node=4 | documentation-only=5 |
| `tester.coverage` | 4 | node=4 | documentation-only=3, strict=1 |
| `coder.backend` | 3 | monolith=1, node=2 | documentation-only=3 |
| `coder.dto` | 3 | node=3 | documentation-only=3 |
| `coder.presentation` | 3 | node=3 | documentation-only=3 |
| `coder.technology` | 3 | node=3 | documentation-only=3 |
| `coder.train` | 3 | node=3 | documentation-only=1, unset=2 |
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
| `coder.types` | 1 | node=1 | strict=1 |
| `tester.telemetry` | 1 | node=1 | documentation-only=1 |
| `tester.test-isolation` | 1 | node=1 | strict=1 |
| `tester.train` | 1 | node=1 | documentation-only=1 |

Two observations for the herd:

- **69 of the 89 are `documentation-only`.** #1714's "Enforceable over documentation-only"
  decision applies to nearly the whole payload: each worker must decide whether a
  locatable per-file violation exists, and reach for `strict`/`advisory` with a detector
  when it does.
- **`coder.design` and `coder.presentation` already have extension-native nodes** — 7 and
  4 of the 18 self-referential `coder.base` incoherences above. Those families need
  reconciliation (is the existing node the mirror, mis-provenanced?) before authoring, or
  the program creates a second node for an obligation that already has one.

## Next, in lifecycle order

1. Adjudicate the 35 incoherences, or #1714's SMOKE gate cannot go green.
2. Create the planner artifacts #1714 names (correction 2) so an acceptance URN exists;
   then the no-silent-drop guard can be written as a RED test rather than the tool here.
3. Per family: classify → (mirror | why-not row) → edges → detector → fixtures.
4. Coverage 128/128 → `coverage.py` exits 0 → #1993's precondition is met.
