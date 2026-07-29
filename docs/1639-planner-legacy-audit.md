# Audit — planner legacy convention monoliths (#1639, Deliverable 1)

**Status:** blocking audit. No convention file was edited to produce this.
**Measured on:** branch `refactor/decommission-planner-legacy-conventions`, base `98b18337`, 2026-07-29.
**Subject:** the 17 files matching `src/atdd/planner/conventions/*.convention.yaml` (4,815 lines).

Every number below is reproducible; the command that produced it is given inline.

---

## 0. Headline — the issue's premise is stale on its central claim

The issue is filed on the claim that `component` and `interface` have **zero nodes** and are a
"total parity failure". **That is no longer true, and has not been since #1111.**

```
$ ls src/atdd/planner/conventions/nodes/ | grep -c '^planner\.component\.'   # 11
$ ls src/atdd/planner/conventions/nodes/ | grep -c '^planner\.interface\.'   #  8
$ git log --oneline -1 -- src/atdd/planner/conventions/nodes/planner.component.urn.convention.yaml
c5e86a9e Re-atomise planner conventions to high-fidelity 1.1.0 convention-nodes (#1111)
```

All 19 nodes are registry-live, and all 19 are already wired into the relationship graph
(25 `source_ref`/`target_ref` occurrences in `src/atdd/coach/graph/relationships.yaml:1265-2059`).

The issue cites `docs/planner-convention-node-parity.md` lines 38-39 as evidence. Those two table
rows are stale. **The same document contradicts them at line 140:**

> `- [x] **A** — component (11), interface (8), train (7) atomised into split nodes.`

**Consequence:** the "atomize `component` + `interface`" half of this issue is already done.
The minimum set of new nodes needed to close the `component` (676L) + `interface` (383L) gap is
**zero**. What is *not* done is enforcement — see §3, which is the real target.

Three further corrections to the issue's measured evidence:

| Issue claim | Measured | Note |
|---|---|---|
| baseline **189** live `planner.*` rules | **191** | 189 node files + `planner.smoke.feedback-loop-close-the-loop` and `planner.smoke.synthetic-fixture-bypass`, which are live without node files. Protect **191**, not 189. |
| `component`/`interface` have 0 nodes | 11 / 8 nodes, all live | see above |
| **8** data-table readers | **2** genuine, faultable readers | 4 of the 8 are docstring citations or a dead constant; see §4 |
| monoliths declare 0 live rules | **confirmed true** | no monolith carries a `rules:` block or a top-level `rule_id`. This is the one claim that holds exactly. |

---

## 1. Verified baseline

```
$ atdd validate planner --local
211 passed, 1 warning   (fast validators)
2 passed, 417 deselected (github_api validators)

$ PYTHONPATH=src python3 -c "from atdd.enforce.registry import core_rule_ids; \
    print(len([r for r in core_rule_ids() if r.startswith('planner.')]))"
191
```

Green. Any plan below must keep it green.

### Deletion is structurally inert

Seven code paths glob the conventions tree. **Every one of them keys on `rules:` or a top-level
`rule_id`, and no monolith carries either** — so deleting monoliths cannot change their output:

| Consumer | Keys on | Effect of deletion |
|---|---|---|
| `src/atdd/state/dispositions.py:149` | `authored_by_train` + `rules:` | none — monoliths have neither |
| `src/atdd/validators/conventions/_support/graph_loader.py:253` | `rules:[].id` (pass 1) | none — pass 1 finds nothing in monoliths |
| `src/atdd/validators/conventions/coverage/archetype.py:244` | `rule_id` | none |
| `src/atdd/planner/validators/_orphan_scan.py:32` | `rule_id` | none |
| `src/atdd/enforce/registry.py:119` | `rule_id` | none |
| `src/atdd/coach/validators/test_no_duplicate_rule_representation.py:69` | monolith `rules:[].id` ∩ node `rule_id` | none — intersection already empty |
| `src/atdd/coach/utils/rule_binding.py:315` | `rule_id` | none |

Verified:

```
$ PYTHONPATH=src python3 -c "
import yaml,glob,os
for f in sorted(glob.glob('src/atdd/planner/conventions/*.convention.yaml')):
    d=yaml.safe_load(open(f)) or {}
    print(os.path.basename(f), [k for k in ('rule_id','rules','authored_by_train') if k in d])"
# → every file prints []
```

This is the strongest single result in the audit: **the 4,815 lines are inert prose.** They are read
by agents and humans as authoritative, and by machines not at all.

---

## 2. Per-file classification

Categories per the mandate: **(1) superseded** — fully carried by an existing node; **(2) live data**
— a lookup table with a real code reader; **(3) unatomized normative** — states a rule no node
carries; **(4) dead weight** — neither.

Section→node mapping was derived mechanically from each node's `source.legacy_section` field.

| # | Monolith | Lines | Nodes | Superseded | Live data | Unatomized | Dead weight | Verdict |
|---|---|---:|---:|---|---|---|---|---|
| 1 | `artifact-naming` | 858 | 16 | all 14 sections | — | — | `purpose`, `benefits`, `references`, `changelog` | **delete** |
| 2 | `component` | 676 | 11 | 10 of 11 sections | — | — | `mapping_examples` (illustrative; substantially in `planner.component.derivation`) | **delete** |
| 3 | `feature` | 635 | 14 | 11 sections | `artifact_seeds.verb_selection.lexicon.additional_verbs` (196 verbs) | — | `structure`/`footprint` (`$ref` stubs), `verb_object_enforcement.brand_exceptions` (**empty**) | **rehome 1 table, then delete** |
| 4 | `acceptance` | 583 | 17 | 18 of 19 sections | — (both readers assert *existence*, not values) | — | `structure` (`$ref` stub), `related_resources` | **delete — but see §6 scope collision** |
| 5 | `train` | 452 | 16 | 13 sections | `acceptances.example` (copy-paste exemplar) | — | `structure` (`$ref` stub), `schema_references` | **delete — but see §6 scope collision** |
| 6 | `interface` | 383 | 8 | all 4 sections | — | — | `description` prose | **delete** |
| 7 | `wagon` | 301 | 11 | 6 sections | — (`brand_exceptions` is **empty**) | — | `structure`, `artifact_transformation` (both `$ref` stubs), `verb_object_enforcement` | **delete** |
| 8 | `wmbt` | 264 | 12 | 11 sections | — (its only reader is a dead constant) | — | `structure`, `steps` (both `$ref` stubs) | **delete** |
| 9 | `appendix` | 193 | 4 | all 4 sections | — | — | `purpose`, `related`, `notes` | **delete** |
| 10 | `criteria` | 147 | 6 | all 4 sections | — | — | — | **delete** |
| 11 | `steps` | 147 | 3 | `steps` (9-step taxonomy → 3 nodes) | — | — | — | **delete** |
| 12 | `theme` | 103 | 6 | `taxonomy`, `boundary` | **`taxonomy.theme_zero_token` + `taxonomy.themes`** — real faultable reader | — | — | **KEEP — out of scope, see §6** |
| 13 | `coverage` | 58 | 6 | all 3 sections | — | — | — | **delete** |
| 14 | `issue-body` | 12 | 0 | — | — | — | header-only; grepped by one test for a literal string | **delete** |
| 15 | `plan` | 8 | 0 | — | — | — | header-only, 0 sections | **delete** |
| 16 | `relationship` | 8 | 1 | header-only | — | — | 0 sections | **delete** |
| 17 | `definition` | 4 | 1 | header-only | — | — | 0 sections | **delete** |

### Notes on the classification

**No category-3 content exists.** Across all 4,815 lines there is **not one section stating a
normative rule that no node carries.** This is the second major finding: the decomposition was
complete, and the monoliths retained only superseded copies, `$ref` stubs, and prose furniture.

**`$ref` stubs are the largest dead-weight class.** Five monoliths carry a `structure:` section
whose entire body is a pointer:

```yaml
# feature.convention.yaml
structure: {$ref: 'schemas:planner:feature'}
# wagon / wmbt / acceptance / train — identical shape
```

The schema is the real authority (`src/atdd/planner/schemas/*.json`). These stubs are indirection
with no content. Same for `wagon.artifact_transformation` and `wmbt.steps`.

**`brand_exceptions` is empty in both artifacts** — so the entire `wagon.convention.yaml` read
performed by `planner/naming.py` returns the empty set:

```
$ PYTHONPATH=src python3 -c "from atdd.planner.naming import brand_exceptions; \
    print(brand_exceptions('wagon'), brand_exceptions('feature'))"
frozenset() frozenset()
```

---

## 3. The real gap: 19 declared nodes, 0 enforced

This is what #1639 should actually be about.

```
$ PYTHONPATH=src python3 -c "
import yaml,glob
for f in sorted(glob.glob('src/atdd/planner/conventions/nodes/planner.[ci]*.yaml')):
    d=yaml.safe_load(open(f)); print((d.get('implementation') or {}).get('type'), d['rule_id'])"
```

All 11 `planner.component.*` and all 8 `planner.interface.*` nodes carry
`implementation: {type: none}`, and **not one is bound to a validator**:

```
$ grep -rho 'bind_rule("planner\.[^"]*")' src/ | sort -u | grep -cE 'component|interface'
0
```

Repo-wide, 47 of 189 planner nodes declare `implementation.type: validator` and there are 31
`bind_rule("planner.*")` call sites. Component and interface contribute zero to both.

So the honest statement of the gap is: **the `component` and `interface` conventions are fully
atomized, fully graph-connected, registry-live, and enforce nothing.** They are exactly the
"documentation-only nodes" the brief forbids — already merged.

### What the repo data can actually support

162 plan feature files carry a non-empty `components:` block. Their shape is
`{side: {layer: [{type, count, rationale}]}}` — **not** the `component:{wagon}:{feature}:{name}:{side}:{layer}`
URN shape in `component.schema.json`. Measured against the real corpus:

| Candidate rule | Subject present? | Violations today |
|---|---|---|
| `planner.component.count-limit` (≤8 per feature) | yes — 162 files | **13 features over** (worst: 24 components, `plan/integration_hardening/features/coach_single_command_driver.yaml`) |
| `planner.component.type-catalog` (`type` ∈ catalog) | yes | **83 violations, 26 distinct unknown types** (`adapters`, `schemas`, `prompts`, `ci_gates`, …) |
| `planner.component.layer-assignment` (layer valid for side) | yes | **1** (`backend.assembly`, `plan/enforce_merge_authority/features/run_merge_checks.yaml`) — plus 3 sides absent from the catalog entirely: `devops`, `hooks`, `docs` |
| `planner.component.urn` (URN grammar) | **no** — plan data carries no component URNs | vacuous against `plan/`; only 24 Python files carry `# Component:` headers |
| `planner.interface.*` | yes — 41 wagons + `contracts/_artifacts.yaml` | not measured; `planner.contract.registry-coherence` already covers adjacent ground **advisory** with 5 live violations |

**This is the decisive sequencing constraint.** Binding these rules `strict` turns
`atdd validate planner` red on day one with ~97 violations that are plan-data debt, not code debt.
They must land **advisory** (the disposition vocabulary is
`strict | suppress-and-clean | advisory | documentation-only`, per
`src/atdd/validators/conventions/presence/archetype.py:68`), exactly as
`planner.contract.registry-coherence` does today.

---

## 4. Reader audit — which of the "8 known readers" can be deleted

The issue lists 8. Reclassified by what the code actually does:

| # | Reader (issue's citation) | What it really does | Disposition |
|---|---|---|---|
| 1 | `planner/naming.py:46,47,64` | `:64` reads `feature.artifact_seeds.verb_selection` → **genuine live read** (218-verb lexicon). `:46-47` + `brand_exceptions()` read `wagon`/`feature` `verb_object_enforcement.brand_exceptions`, **both empty** | **retarget `:64`; delete the `wagon` entry and `brand_exceptions()` dead path** |
| 2 | `planner/validators/test_wmbt_vocabulary.py:36` | `WMBT_CONVENTION` is **assigned and never referenced** — a dead constant. The vocabularies below it are hardcoded Python literals | **delete the constant** (not a reader) |
| 3 | `planner/validators/tests/test_train_acceptance_authorable.py:33,85` | reads `train.acceptances.example`, asserts the human-copyable exemplar validates | **retarget** to `planner.train.acceptances` (node must gain the exemplar) |
| 4 | `tester/validators/test_acceptance_urn_separator.py:47` | reads `acceptance.urn_generation.pattern` + `.example`; the pattern is already carried by node `planner.acceptance.urn-generation` (`terms[acceptance_urn].values.pattern`) | **delete** — asserts prose a node now carries |
| 5 | `tester/validators/tests/test_hermetic_integration_fixtures.py:66` | asserts `acceptance.convention.yaml` *declares* `execution_kinds:`/`boundary_kinds:`/`harness_codes:`. Pure existence-of-prose assertion; nodes `planner.acceptance.execution-kind`, `.boundary-kind-vocabulary`, `.harness-vocabulary` carry the vocabularies | **delete that one test** (the file's other tests are real) |
| 6 | `validators/conventions/presence/archetype.py:73` + `presence/test_theme_zero_mandatory.py:40` | `_check_theme_zero_mandatory` parses `theme.taxonomy` through `graph.root`; the test fault-injects by mirroring the real file. **This is the only genuinely faultable data reader in the set** | **KEEP — out of scope, §6** |
| 7 | `coder/validators/test_train_urns.py:42,293` | asserts the file exists and contains a `urn_naming.theme_orchestrator_urn` key. Existence-of-prose; node `planner.train.theme-orchestrator-urn` carries it | **delete that one test** |
| 8 | `src/atdd/tests/test_Y005_...:190` | greps `issue-body.convention.yaml` for a hardcoded `pip install` string | **delete** with the file |

Two readers the issue names that are **not readers at all**:
`planner/validators/_theme_taxonomy.py:10` and `coach/utils/theme_map.py:20` are docstring
citations. Likewise `coach/commands/interface.py:697` takes a `convention_path` parameter that the
function body never uses (URN parsing is hardcoded at `:707`), and
`coach/commands/test_interface.py:56` **writes its own fixture** into a tmpdir rather than reading
the shipped file.

**Score: of 8 nominal readers, 4 can be deleted outright, 2 are non-readers, 1 is retargeted, 1 is
out of scope.** Deleting a validator that asserts prose a node now enforces is strictly correct —
it is a test of documentation, not of behaviour.

### Citation retargeting

The issue estimates "~30 docstring `Convention:` citations". Measured:

```
$ grep -rn --include='*.py' -oE "\b(acceptance|appendix|artifact-naming|component|...)\.convention\.yaml" src/ | wc -l
88          # all .py mentions, mostly inline prose
$ grep -rnE "^\s*(#\s*)?Convention:?\s+.*planner/conventions/[a-z-]+\.convention\.yaml" src/ | wc -l
7           # structured `Convention:` docstring headers
$ grep -rn --include='*.md' -oE "...\.convention\.yaml" docs/ *.md | wc -l
14          # markdown
```

Of those 7 structured headers, **3 point at `theme.convention.yaml`, which is being kept** (§6), so
only **4 need retargeting** — 2 at `issue-body`, 1 at `wagon`, 1 at `wmbt`. The other 81 `.py` mentions are prose and can be swept
mechanically or left; they are not machine-read. This is a much smaller job than "~30".

---

## 5. Where the data tables should live

**Recommendation: do not create `src/atdd/planner/data/`.**

After eliminating dead constants, empty tables, `$ref` stubs and existence-assertions, the set of
live tables needing a home is **one**:

- `feature.artifact_seeds.verb_selection.lexicon.additional_verbs` — 196 verbs, read by
  `planner/naming.py:64` to build the 218-verb lexicon.

A new top-level package directory for one table is unjustified overhead, and it recreates the exact
problem the issue names: a data file living apart from the rule it serves. The node
`planner.feature.verb-selection-by-artifact-type` **already carries the other half of this table**
(`terms[verbs_by_type].values` = the 4 `by_artifact_type` buckets) and is already the rule's home.

**So: each table follows its single consumer, and for this table the consumer's convention node
already exists.** Add `additional_verbs` as a second term on that node and point `naming.py` at the
node. Net new files: zero. Net new directories: zero.

This also answers the issue's Decision #2 more sharply than the issue does: the parity ledger puts
*data* out of scope for nodes, but this is not free-floating data — it is the **extension of a rule's
vocabulary**, which is precisely what a node's `terms[].values` block is for (see
`planner.acceptance.harness-vocabulary`, `planner.component.type-catalog`, both of which already
carry substantially larger tables the same way).

The `theme.taxonomy` table is the one case that would justify a data home — and it is out of scope.

---

## 6. Scope collision — 3 files cannot be deleted under this issue

The issue's Done-when requires:

> No `src/atdd/planner/conventions/*.convention.yaml` remains.

Its Out of Scope says:

> Extracting the shared vocabulary (train URN / theme taxonomy / acceptance URN grammar) consumed
> by coder, tester and coach validators. Separate issue.

**These contradict on exactly three files.** `theme`, `train` and `acceptance` are the carriers of
the three named vocabularies, and each has a cross-archetype reader:

| File | Vocabulary | Cross-archetype reader |
|---|---|---|
| `theme.convention.yaml` | theme taxonomy | `src/atdd/validators/conventions/presence/archetype.py:73` (**faultable**, with a fault-injection test that mirrors the file's bytes) |
| `train.convention.yaml` | train URN | `coder/validators/test_train_urns.py:42` |
| `acceptance.convention.yaml` | acceptance URN grammar | `tester/validators/test_acceptance_urn_separator.py:47` |

For `train` and `acceptance` the readers are prose-existence assertions and can simply be deleted
(§4), so those two files *can* go. **`theme` cannot**: `_check_theme_zero_mandatory` performs a real
data-level check that `test_theme_zero_mandatory.py` faults by mirroring the file, and the module
docstring at `archetype.py:129` states this variant exists specifically to add "the real, data-level
gate over `theme.convention.yaml` that legacy lacks". Deleting the file without rehoming the
taxonomy removes a live gate — and rehoming the taxonomy is explicitly the separate issue.

**Recommendation:** amend the Done-when to *16 of 17*, and leave `theme.convention.yaml` (103L) to
the shared-vocabulary issue, which is where its reader lives. Deleting 16 of 17 files and 4,713 of
4,815 lines achieves the issue's stated user impact in full. Forcing the 17th means either doing
the out-of-scope work or dropping a live gate.

---

## 7. Revised plan

This supersedes the In-Scope list. Ordered to keep `atdd validate planner` green at every commit —
which it can be, throughout, because the only steps that could redden it (validator binding) come
last and land advisory.

**Guiding principle: the atomization is done; the work is enforcement plus deletion.** Zero new
nodes are authored. That is the efficiency answer the issue asks for.

### Step 1 — Correct the stale parity ledger

Fix `docs/planner-convention-node-parity.md` lines 38-39 (and the §"never decomposed" narrative at
46-54) to match line 140 and the filesystem. This is first because every later step's rationale
depends on the corrected record, and because leaving it is how #1639 got mis-filed.

- **Acceptance:** the ledger's `component`/`interface` rows read 11 / 8 with ✅; no line in the
  document asserts zero nodes.
- **Gate:** `atdd validate planner --local` (expect 211 passed, unchanged)

### Step 2 — Rehome the one live table

Add `additional_verbs` (196 verbs) as a term on the **existing** node
`planner.feature.verb-selection-by-artifact-type`, via the canonical authoring path. Repoint
`planner/naming.py:64` at the node. Delete the now-dead `wagon` entry from `_CONVENTION_FILES` and
the `brand_exceptions()` path that reads it (both tables are empty).

- **Acceptance:** `verb_lexicon()` still returns exactly **218** verbs; `naming.py` no longer opens
  any file under `conventions/*.convention.yaml`.
- **Gate:**
  ```
  PYTHONPATH=src python3 -c "from atdd.planner.naming import verb_lexicon; \
      assert len(verb_lexicon())==218, len(verb_lexicon()); print('218 OK')"
  atdd validate planner --local
  ```

### Step 3 — Retarget the one real reader

Give node `planner.train.acceptances` the copy-paste exemplar from `train.acceptances.example`, and
point `planner/validators/tests/test_train_acceptance_authorable.py:33,85` at the node.

- **Acceptance:** the test passes reading only the node; no path to `train.convention.yaml` remains
  in `src/atdd/planner/`.
- **Gate:** `python -m pytest src/atdd/planner/validators/tests/test_train_acceptance_authorable.py -q`

### Step 4 — Delete the prose-asserting validators

Delete, per §4: the `test_train_convention_file_exists` test in `coder/validators/test_train_urns.py`;
`tester/validators/test_acceptance_urn_separator.py`; the
`test_e006_unit_001_convention_declares_hermetic_vocabularies` test in
`tester/validators/tests/test_hermetic_integration_fixtures.py`; the `issue-body` assertion in
`src/atdd/tests/test_Y005_...:190`; and the dead `WMBT_CONVENTION` constant at
`planner/validators/test_wmbt_vocabulary.py:36`.

Each asserts that a *file contains prose*. The corresponding node already carries the vocabulary, so
nothing is lost. Nothing is deleted here whose subject is behaviour.

- **Acceptance:** live `planner.*` rule count still **191**; no test reads a planner monolith except
  the theme pair.
- **Gate:**
  ```
  PYTHONPATH=src python3 -c "from atdd.enforce.registry import core_rule_ids; \
      n=len([r for r in core_rule_ids() if r.startswith('planner.')]); assert n==191, n; print('191 OK')"
  atdd validate all --local
  ```

### Step 5 — Delete 16 monoliths

Delete all except `theme.convention.yaml` (§6). 4,713 lines removed. Retarget the 4 structured
`Convention:` docstring headers that point at a deleted file in the same commit (the other 3 point
at `theme` and stay valid).

Safe by §1: no glob consumer keys on anything a monolith carries. After steps 2-4 no code opens any
of the 16.

- **Acceptance:** `ls src/atdd/planner/conventions/*.convention.yaml` lists exactly one file,
  `theme.convention.yaml`; rule count still 191.
- **Gate:**
  ```
  atdd validate all --local
  atdd enforce --repo-root . --paths src/atdd --ratchet .atdd/enforce-ratchet.yaml
  ```

### Step 6 — Close the enforcement gap (the actual target)

Bind validators to the existing component/interface nodes, in
`src/atdd/planner/validators/`, each calling `bind_rule("planner.<short>.<rule>")` at module import
and flipping the node's `implementation` from `none` to `validator`.

Land the four with a real, measured subject — **advisory**, per §3:

| Rule | Subject | Landing violations |
|---|---|---|
| `planner.component.count-limit` | 162 feature `components:` blocks | 13 |
| `planner.component.type-catalog` | `type:` values vs the catalog | 83 |
| `planner.component.layer-assignment` | layer/side validity | 1 (+3 uncatalogued sides) |
| `planner.interface.orphan-detection` | 41 wagons vs `contracts/_artifacts.yaml` | to be measured |

**Do not bind `planner.component.urn`** — plan data carries no component URNs, so the validator
would be vacuous. Say so in the node rather than shipping a green-by-emptiness gate.

The remaining 15 nodes stay `implementation: none`. **Flagging honestly:** that leaves them as
documentation-only nodes, which the brief forbids for nodes *authored here*. Since none are authored
here, the prohibition does not bite — but the condition the brief is aiming at persists, and closing
it for all 19 is a larger piece of work than #1639 as scoped. Recommend a follow-up issue rather
than either padding this one or shipping 15 vacuous validators to satisfy a count.

- **Acceptance:** 4 rules move to `implementation.type: validator` with a bound validator; rule
  count ≥ 191; the ~97 violations report as advisory, not failures.
- **Gate:**
  ```
  atdd validate planner --local
  atdd validate all --local
  atdd enforce --repo-root . --paths src/atdd --ratchet .atdd/enforce-ratchet.yaml
  ```

### Sequencing rationale

Steps 1-5 cannot redden the gate: they delete inert prose and tests-of-prose, and the one live table
moves before its file is deleted. The only step that changes enforcement behaviour is 6, and it lands
last and advisory. **The window where `atdd validate planner` is red is zero** if step 6 lands
advisory; it is ~97 violations wide if any rule lands strict.

Reordering 6 before 5 would mean writing validators against nodes whose monolith twin still exists —
inviting the duplicate-representation trap. Reordering 2 after 5 would delete `feature.convention.yaml`
while `naming.py` still reads it, breaking `verb_lexicon()` and every verb-object validator with it.

---

## 8. Answers to the four efficiency questions

1. **Minimum new nodes to close the `component` + `interface` gap:** **zero.** All 19 exist, are
   live, and are graph-connected. The gap is enforcement, not declaration (§0, §3).
2. **Readers deletable rather than retargeted:** **4 of 8** deleted outright, 2 were never readers,
   1 retargeted (`test_train_acceptance_authorable`), 1 out of scope (`theme`) (§4).
3. **Is `planner/data/` the right home?** **No.** After eliminating empty tables, `$ref` stubs and
   existence-assertions, exactly one live table remains, and its rule's node already carries the
   other half of it. Each table follows its consumer; net new directories zero (§5).
4. **Order minimising the red window:** ledger → rehome → retarget → delete tests → delete
   monoliths → bind validators advisory. **Red window: zero** (§7).

## 9. Recommended amendments to #1639

1. **Drop** "atomize `component` + `interface`" — done in #1111. Replace with "bind validators to the
   19 existing, unenforced component/interface nodes".
2. **Correct** the baseline from 189 to **191**.
3. **Amend** Done-when from "no `*.convention.yaml` remains" to "16 of 17 deleted;
   `theme.convention.yaml` deferred to the shared-vocabulary issue" (§6).
4. **Correct** the reader count from 8 to 2 genuine readers (§4).
5. **File a follow-up** for the 15 component/interface nodes that stay unenforced after step 6.
