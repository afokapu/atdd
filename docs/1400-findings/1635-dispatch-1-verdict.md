# Dispatch 1 verdict — does `38bd9f33` already fix #1676?

> Investigated 2026-08-02 in `/Users/alecfokapu/Github/atdd/feat-issue-feature-binding-resolves-wmbts`
> on `feat/issue-feature-binding-resolves-wmbts`. Nothing was minted, no transition was run,
> no live issue was mutated. Every measurement below used a throwaway control root under the
> session scratchpad, a throwaway work item (#93777 / #93778), and a stub `gh`, except where
> explicitly marked as a read-only query against the live store or GitHub.

---

## THE ANSWER: **Partially — and your provisional answer is confirmed, with one correction and one addition.**

Confirmed:

- `38bd9f33` **kills #1676's structural claim.** A writer for the typed `data.feature` field now
  exists on the `--revise` path and it works. On `main` the same command exits 2 and refuses.
- `38bd9f33` **does not touch #1676's literal defect.** `atdd update --feature-urn` still exits 0,
  still reports `Updated #N`, and still leaves `data.feature` untouched. `src/atdd/cli.py` and
  `src/atdd/coach/commands/issue.py` are both byte-identical to `main` on this branch.

**Correction to your framing** — Route A does not "write nothing". It writes, to the **wrong key**.
`IssueManager._apply_text_updates` deposits the value under `data.feature_urn`; every reader in the
codebase reads `data.feature`. That is a sharper defect than a no-op: the store *does* change, so a
naive "did the store move?" check passes while the binding stays unset. This is the single most
important correction in this document, because it changes what a fix has to do.

**Correction to #1676's third claim** — "writes a WRONG urn into the issue body" is **refuted for
`atdd update` itself**. That command has no body-write path at all. What the reporter actually
observed on #1622 is real but is a *divergence*, not a corruption: the body carries the intended
urn and the store's typed column is `NULL`. Same disease, wrong attribution.

**Addition** — `38bd9f33`'s own writer is **store-only**. `--revise --feature <urn>` alone updates
`data.feature` and leaves the body's `Feature` row saying whatever it said before. So Route B, used
as the fix for #1676, *creates* the body↔store divergence that #1676's own done-when forbids. The
branch's new C011 validator then correctly flags it — advisory.

**So #1676 is not "build a writer".** It is, precisely:

1. repoint or fail-close `atdd update --feature-urn` (it currently writes a dead key, unvalidated,
   exit 0); and
2. close the body half of the write that `38bd9f33` left open.

Neither duplicates `38bd9f33`. Both are small.

---

## Evidence

### Build provenance — read this before trusting anything below

**MEASURED.** `which atdd` → `/Users/alecfokapu/.local/bin/atdd`, shebang
`/Users/alecfokapu/.local/pipx/venvs/atdd/bin/python`, `atdd --version` → `4.33.0`. The pipx
install is a **plain (non-editable) copy** — `site-packages/atdd/` is a real directory and there is
no `direct_url.json` — so the shipped CLI is *not* this worktree's tree.

**MEASURED.** For the four files that matter, installed 4.33.0 is byte-identical to `origin/main`:

```
$ for f in state/work_item_writer.py planner/commands/author.py \
           planner/commands/author_publish.py coach/commands/issue_lifecycle.py; do
    git show origin/main:src/atdd/$f > /tmp/mainf.py && diff -q /tmp/mainf.py $SITE/$f && echo SAME $f; done
SAME  state/work_item_writer.py
SAME  planner/commands/author.py
SAME  planner/commands/author_publish.py
SAME  coach/commands/issue_lifecycle.py
```

**Therefore the installed 4.33.0 CLI is a faithful `main` baseline**, and every A/B below is a real
branch-vs-main comparison. The branch tree is exercised as
`PYTHONPATH=$PWD/src <pipx-python> -m atdd …`, which resolves `atdd.__file__` to this worktree
(verified).

### The two facts you asked me to falsify — both confirmed

**Fact 1 — MEASURED, confirmed with a line-number correction.**
`--feature-urn` is declared at `src/atdd/cli.py:803` (exactly as stated). The dispatch is at
`src/atdd/cli.py:2293` (`manager = IssueManager()`) → `manager.update(...)` with
`feature_urn=getattr(args, 'feature_urn', None)` at **`src/atdd/cli.py:2298`**, not 2308. The
target is `IssueManager.update` at `src/atdd/coach/commands/issue.py:1574` — the orphaned manager.
`diff src/atdd/cli.py $SITE/cli.py` → **IDENTICAL**, so the 4.33.0 upgrade changed nothing here.

**Fact 2 — MEASURED, confirmed.**

```
$ git log --oneline origin/main..HEAD -- src/atdd/cli.py
(empty)
$ git log --oneline origin/main..HEAD -- src/atdd/coach/commands/issue.py
(empty)
```

#1635 never touched either file. The command #1676 names is untouched by this program.

### Route A — `atdd update <N> --feature-urn <urn>`

Throwaway store, work item #93777 seeded with `feature: None` and a schema-valid body whose
`Feature` row already names the target urn. **MEASURED**, both builds:

| Surface | BRANCH tree | INSTALLED 4.33.0 (= `main`) |
|---|---|---|
| exit code | **0** | **0** |
| stdout | `Updated #93777:` / `  feature_urn: feature:govern-lifecycle:bind-issue-feature` | identical |
| store `data.feature` | **`None` — unchanged** | **`None` — unchanged** |
| store `data.feature_urn` | **written** to the passed urn | **written** to the passed urn |
| body `Feature` row | unchanged | unchanged |

Repeated with a URN that resolves to nothing in `plan/`
(`feature:govern-lifecycle:no-such-feature-exists`): **exit 0** on both builds, `data.feature_urn`
set to the garbage value, `data.feature` still `None`, body untouched. **There is no validation on
this route at all.**

**The wrong-key mechanism — MEASURED (source read + grep), `src/atdd/coach/commands/issue.py`:**

```
1628  updated.extend(self._apply_text_updates(issue_number, branch, train, feature_urn, archetypes))
1691  def _apply_text_updates(...):
1703      text_updates = {"branch": branch, "train": train,
1705                      "feature_urn": feature_urn,        # <-- the key that is written
1706                      "archetypes": archetypes}
1708      manifest_text = {k: v for k, v in text_updates.items() if v}
1712      self._update_manifest_fields(issue_number, manifest_text)
1713      return [f"{key}: {value}" for key, value in manifest_text.items()]
```

Every reader uses `feature`, not `feature_urn`:
`src/atdd/state/work_item_reader.py:48` `_FEATURE_KEY = "feature"`;
`src/atdd/coach/gate/smoke_obligation.py:93` `FEATURE_KEY = "feature"`;
`src/atdd/state/work_item_writer.py:194` `updates["feature"] = feature`.
`grep -rn 'feature_urn' src/atdd --include='*.py'` (tests excluded) returns **no reader of
`work_item.data["feature_urn"]`** anywhere — every hit is an unrelated local or dataclass field.
The key is write-only.

**Two further silent-success layers — MEASURED (source read):**
`_store_update_fields` (`issue.py:347`) returns `bool` and swallows every exception
(`except Exception … return False`); `_apply_text_updates` **discards that return value** and
reports the field as updated regardless. So even a store write that genuinely failed would print
`Updated #N`. This is the operational law in its purest form.

**Live fingerprint of the defect — MEASURED, read-only query against the live store:**

```
#1622: feature=None  feature_urn='feature:migrate-projection-authority:migrate-store-projection'
```

#1622 is the very issue #1676 was filed from. Its production work item carries the operator's urn
in the dead key and `NULL` in the typed one. That is `atdd update --feature-urn` having been run
for real, preserved in the store.

### Route B — `atdd author issue --revise <N> --feature <urn>`

**MEASURED**, same throwaway store, same seeded item:

| Surface | BRANCH tree | INSTALLED 4.33.0 (= `main`) |
|---|---|---|
| exit code | **0** | **2** |
| stderr | `feature binding set to feature:govern-lifecycle:bind-issue-feature` + `revised work_item …` | `--revise requires --body-file and/or explicit --type` |
| store `data.feature` | **written correctly** | **`None` — unchanged** |

That is #1676's "create-only" claim confirmed on `main` and closed on the branch.

Fail-close behaviour on the branch — **MEASURED**, refusals leave the prior binding intact:

| Input | exit | store after | message |
|---|---|---|---|
| `feature:govern-lifecycle:no-such-feature-exists` | **2** | unchanged | `invalid --feature: … resolves to nothing in plan/ (expected …/no_such_feature_exists.yaml)` |
| `train:issue-lifecycle:drive-state-machine` (the #1626 drift) | **2** | unchanged | `'train:…' is not a feature identity; expected feature:<wagon>:<name>` |

**The body half is NOT closed — MEASURED.** Seeded a body declaring
`feature:govern-lifecycle:bind-issue-feature`, then ran `--revise --feature
feature:govern-lifecycle:second-probe-feature`:

```
exit 0
store.feature  = feature:govern-lifecycle:second-probe-feature   <-- moved
body.Feature   = | Feature | `feature:govern-lifecycle:bind-issue-feature` |   <-- did not
```

`--feature` alone writes the store and not the body. #1676's done-when is *"persists `data.feature`
= X **and writes the SAME urn to the body**"*. Route B satisfies the first clause only.

### Which of #1676's claims survive `38bd9f33`

| #1676 claim | Verdict | Basis |
|---|---|---|
| `atdd update --feature-urn` exits 0 / reports success | **SURVIVES** | measured, both builds |
| …and `data.feature` stays `None` | **SURVIVES, but restated**: it writes `data.feature_urn`, a key no reader reads — not a no-op, a wrong-key write | measured + grep |
| …and writes a WRONG urn into the issue body | **DEAD as stated.** `atdd update` has no body-write path. The real fault on #1622 is body↔store *divergence*: body carries the intended urn, store's typed column is `NULL` | measured (live #1622 read) + source read |
| "the ONLY field-setter for `data.feature`; there is no workaround" | **DEAD on this branch**, still true on `main` | measured A/B (exit 0 vs exit 2) |
| Exit code should be non-zero on write failure | **SURVIVES** — Route A exits 0 even for a URN that resolves to nothing | measured |
| Done-when: store and body carry the same urn | **SURVIVES for both routes** — A writes neither, B writes only the store | measured |

**INFERRED (scoping, not measurement):** #1676 reduces to two small changes — (a) repoint
`IssueManager.update`'s `feature_urn` onto `revise_work_item_issue(feature=)` so it reuses
`38bd9f33`'s validated writer, or make it exit non-zero and name the replacement command; and (b)
project the accepted binding onto the body's `Feature` row on the `--revise` path. Neither
re-implements `38bd9f33`; (a) explicitly consumes it.

---

## 1. Is the WMBT read side actually finished?

**Build established first, as instructed.** The pipx 4.33.0 CLI is `main`, so its output says
nothing about this branch; both builds were run.

`atdd coach issues 1635` **does not reach the display** from this worktree on **either** build —
**MEASURED**:

```
Error: Directory already exists: /Users/alecfokapu/Github/atdd/feat-issue-feature-binding-resolves-wmbts
Error: Failed to create worktree branch.
```

`coach issues <N>` → `issue_read.run` → `IssueLifecycle.enter`, which for a `_BRANCH_STATUSES`
issue calls `_is_in_worktree(slug, prefix)`; that returns False *while standing in the correct
worktree*, `_find_worktree_for_issue` also returns None, and it falls through to `_create_branch`,
which fails on the existing directory. **This is a separate, pre-existing bug** — it is not caused
by `38bd9f33` (`issue_lifecycle.enter`'s worktree logic is unchanged on this branch) and it blocks
the documented read command for every issue whose worktree already exists. Surfacing, not fixing.

I therefore drove `IssueLifecycle._reenter_display_only(N)` — the same `_print_context` path, minus
worktree creation — on both builds. **MEASURED:**

```
########## INSTALLED (== main) — #1635 ##########
  Status:  RED
  WMBTs: none found

########## BRANCH TREE — #1635 ##########
  Status:  RED
  WMBTs: 1 declared by feature:govern-lifecycle:reliable-manifest-registration
    - wmbt:govern-lifecycle:E008  (…/plan/govern_lifecycle/E008.yaml)
```

**"none found" is gone, and the resolver reads real WMBTs off disk.** The three-outcome rendering
works — **MEASURED** on the branch for issues with no binding:

```
#1676  WMBTs: no feature binding — this issue declares no feature, so its decomposition cannot be located.
              Set one: atdd author issue --revise 1676 --feature <urn>
#1622  (same)
#1655  (same)
```

`_fetch_sub_issues`, the `gh issue list --label atdd-wmbt` search, and the literal `"none found"`
are all **absent** from `src/atdd/coach/commands/issue_lifecycle.py` on this branch and all
**present** on `main` (grep, both trees). The branch's own suite holds: **MEASURED**,
`pytest src/atdd/coach/validators/tests -k "y006 or c011 or l003 or binding" -q` →
**54 passed, 287 deselected**.

**But the read side is finished and the data underneath it is not.** Three findings:

1. **#1635's own binding is wrong.** **MEASURED** (live store + live GitHub body):
   store `data.feature = feature:govern-lifecycle:reliable-manifest-registration`, while the body's
   `Feature` row says `feature:govern-lifecycle:bind-issue-feature` — the feature this program
   actually authored. That is why the WMBT section resolves `E008` and not the `Y006` this program
   built. The branch's own C011 scanner catches it — **MEASURED**, run over live records:

   ```
   3 coach.issue.feature-binding-must-resolve github-issue#1635:feature
     the issue body declares feature feature:govern-lifecycle:bind-issue-feature but the store holds
     feature:govern-lifecycle:reliable-manifest-registration — the two records disagree and a reader
     cannot tell which is authoritative
   3 coach.issue.feature-binding-must-resolve github-issue#1622:feature
     feature feature:migrate-projection-authority:migrate-store-projection resolves to nothing in plan/
   3 coach.issue.feature-binding-must-resolve github-issue#1676:feature   (same)
   ```

   Disposition is **advisory** (`coach.issue.feature-binding-must-resolve.convention.yaml:48-49`,
   `severity: 3`), so it reports and does not block.

2. **The backfill has no CLI surface.** **MEASURED** —
   `grep -rn backfill_feature_bindings src/atdd --include='*.py'` returns exactly two hits: the
   definition at `src/atdd/coach/commands/issue_feature_binding.py:156` and one test. No `cli.py`
   wiring, no `atdd` verb. An operator cannot run it.

3. **The backlog is large and only partly derivable.** **MEASURED**, `dry_run=True` (no writes)
   against the live store: **`would_write=177, unresolved=531`** — 708 work items carry no
   `data.feature`, and the body-derivation rule (correctly refusing to guess) can only rescue 177
   of them. The remaining 531 need an authored binding.

**Verdict on item 1:** the read side is done and demonstrably better than `main`. The write side is
half done (store yes, body no), the repair tool is unreachable, and 531 issues will still render
"no feature binding" after everything on this branch runs.

---

## 2. Overlap check

**Issues — MEASURED (`gh issue view`, state + labels) plus source reads for the overlap judgement:**

| # | State | One line | Overlaps a #1635 seam? |
|---|---|---|---|
| **#1676** | OPEN, `atdd:INIT` | `atdd update --feature-urn` is a silent no-op | **Yes, directly** — and now *partly shipped*: its structural claim is dead, its literal claim is untouched. Remaining scope is the two small changes above. Must not re-implement the writer. |
| **#1609** | OPEN, `atdd:INIT` | Make a feature declaring integration components reach a `live_smoke` acceptance (planner rules C011/C012) | **Adjacent, not overlapping.** Its body puts *"Changing `atdd.coach.gate.smoke_obligation`"* explicitly **out of scope**. It supplies the plan-side obligation; #1635/#1676 supply the issue-side binding that obligation is reached *through*. Complementary — see item 3. |
| **#1550** | OPEN, `atdd:INIT` | Change `planner.wmbt.must-have-smoke-acceptance` from ownership to coverage, in place, advisory | **No.** Operates on WMBT→acceptance inside `plan/`; #1635 operates on issue→feature. No shared file. |
| **#1576** | OPEN, `atdd:INIT` | Umbrella only, lands no code: make wagons adopt cargo/interlocking, then enforce SMOKE by topology (parents #1550/#1551/#1552/#1553/#1565) | **No** (umbrella). Worth noting its child **#1565 "bind issues to route-space"** is the nearest neighbour to #1635's issue-side binding — check before minting anything in that direction. |
| **#1553** | OPEN, `atdd:INIT` | Adjudicate the 149 SMOKE suppressions, then advisory → ratchet → strict | **No.** Downstream of #1550's rule change; touches suppression markers, not bindings. |

**Adjacent worktrees — MEASURED:**

- **`refactor/recompose-wagons-from-wmbts`** (`/Users/alecfokapu/Github/atdd/refactor-recompose-wagons-from-wmbts`,
  `684d4ea9`). `git diff --stat origin/main...` over `src/` is **empty** — the branch is
  `docs/` and `plan/` only (recomposition specs, URN maps, a 152-artifact contract map, ADR-001).
  It **re-plans** the wagon/feature/WMBT decomposition on paper; it changes no code and no
  resolver. **No overlap with #1635's seams**, but note it proposes URN churn — a large-scale
  rename of the very feature URNs #1635 now binds issues to. Sequencing risk, not code conflict.
- **`refactor/reconcile-wmbt-schema-with-validation-reality`** (`/Users/alecfokapu/Github/atdd/refactor-reconcile-wmbt-schema`,
  `090288bf`). Touches `wmbt.schema.json`, `acceptance.schema.json`, two planner conventions, two
  tests. Its substance **already merged to `main`** as `c44160b9 refactor(atdd): Reconcile WMBT +
  acceptance schema with validation reality (#760) (#1162)`; what remains on the branch is a stale
  44-line schema delta plus manifest-mirror noise. **Effectively already-shipped.** Neither branch
  touches `issue_lifecycle`, `feature_binding`, `smoke_obligation`, `work_item_writer`, or any
  `author*` module (grep over both diffs: zero hits).

---

## 3. The `live_smoke_obligation` vacuous pass

**Code path confirmed — MEASURED (source read).**
`src/atdd/coach/gate/smoke_obligation.py:124-155`: `live_smoke_obligation` accumulates from
`data[FEATURE_KEY]` (`"feature"`, line 93) and `data[TRAIN_KEY]`. A `None` feature contributes
nothing to `scopes` and nothing to `urns`. `SmokeObligation.__bool__` is `bool(self.acceptance_urns)`.
`src/atdd/coach/gate/smoke_execution_check.py:146-148`:

```python
obligation = live_smoke_obligation(ctx.worktree, work_item_data(store, uid))
if not obligation:
    return self._not_applicable(ctx, transition, uid, obligation)
```

→ SMOKE→REFACTOR **passes as "not applicable."**

**Measured live, read-only, against the real store and this worktree's `plan/`:**

```
#1655: feature=None  train=None
       obligation=False  owed=()  scopes=()
       'its work item declares no plan scope (no feature, no train)'
#1676: same — obligation=False, scopes=()
#1622: feature=None  train='train:object-conflict-resolution:project-state'
       obligation=False  owed=()  scopes=('train:object-conflict-resolution:project-state',)
#1635: feature='feature:govern-lifecycle:reliable-manifest-registration'
       train='train:issue-lifecycle:drive-state-machine'
       obligation=False  owed=()  scopes=(both)
```

The brief's claim is confirmed exactly on #1655, and #1635 shows the *second* flavour: a binding
that resolves, walked all the way through `plan/`, still yielding `owed=()`.

**Does `38bd9f33` change it? NO — MEASURED:**

```
$ git log --oneline origin/main..HEAD -- src/atdd/coach/gate/
(empty)
```

The branch touches nothing under `src/atdd/coach/gate/`. It changes the *inputs* (more issues will
carry a resolvable `feature`), never the gate.

**Does #1609 already own it? Partly — INFERRED from its body (read via `gh`), which is explicit:**
#1609 owns the **plan-side** half — "a feature declaring a non-zero `components.backend.integration`
count must reach at least one `execution_kind: live_smoke` acceptance" — and names
*"Changing `atdd.coach.gate.smoke_obligation`. Its opt-in shape is correct"* as **out of scope**.

**#1609 is necessary and not sufficient, and the measurements show why.** Its rule fires on
features. An issue whose `data.feature` is `NULL` reaches no feature, so no #1609 rule can ever be
consulted for it — `scopes=()`, as measured on #1655 and #1676. With 708 unbound work items live
(and 531 of them not derivable from a body), #1609 alone would leave the gate vacuous for the
majority of the repo. **The binding is the prerequisite; #1609 is the obligation.** They are
complementary and should be sequenced binding-first, not treated as overlapping.

---

## 4. #1635's own lifecycle lag

**All three surfaces — MEASURED:**

| Surface | Value | How |
|---|---|---|
| CLI display | `Status:  RED` | `IssueLifecycle._reenter_display_only(1635)`, both builds |
| Store `objects.state` | `'RED'` | `WorkItemReader().get(1635)` → `uid=issue-feature-binding-resolves-wmbts state='RED'` |
| GitHub label | `atdd:RED` | `gh issue view 1635 --json labels` → `["atdd-issue","atdd:RED"]` |

**All three agree.** There is no store↔label divergence here — the lag is between the *phase* and
the *work on the branch*: `38bd9f33 feat(green):` is committed and its 54 acceptances pass, while
the phase still says RED.

**Correct next transition: `RED → GREEN`.** — **MEASURED**,
`src/atdd/coach/conventions/phase_machine.convention.yaml:49-52`:

```yaml
RED:
  agent: coder
  transitions_to: [GREEN, BLOCKED, OBSOLETE]
  autonomy: agent
```

`autonomy: agent`, and only `PLANNED→RED` is in `DEFAULT_GATED_TRANSITIONS` — so no new approval
token is required. `.atdd/runtime/issue-1635/approvals/` holds only `PLANNED-RED.json`, which is
consistent and needs nothing added.

**NOT RUN.** `atdd coach transition` is denied in `.claude/settings.local.json` and reserved to you.
The command, for when you choose to run it:

```
atdd coach transition 1635 GREEN
```

**One blocker you should know about first — MEASURED:** PR #1648 is `state=OPEN draft=true
mergeable=CONFLICTING`. The branch conflicts with `main` and will need a merge before it can land,
independent of the phase.

---

## Things I must surface rather than route around

1. **Another writer is active in this worktree, concurrently with this session.** Commit
   `55439f33 fix(planner): observably react when a feature YAML is unreadable (#1635)` landed at
   `2026-08-02 19:15:18 -0300`, ~7 minutes after my docs commit `8e99e623` (19:08:48) and while I
   was mid-investigation. I did not author it; `git reflog` shows it as a plain `commit:` entry
   between my own. Its validator run then rewrote `.atdd/baselines/validation/planner.yaml`
   (`passed_at: 2026-08-02T22:15:29Z`, `atdd_version: 4.33.0`, `skipped_api: true`). If a second
   agent is dispatched here, you have two writers on one branch.

2. **The three dirty baselines are now one.** At session start `coach.yaml`, `planner.yaml`,
   `tester.yaml` were modified; only `planner.yaml` is now, and its diff is the 19:15:29 rewrite
   above, not mine. **I committed none of them** and touched none of them. Flagging because the
   brief described the pre-existing state and it has changed underneath us.

3. **`atdd coach issues <N>` is unusable from inside an existing worktree** (see item 1). This
   blocked the exact command the brief asked me to run. I used the display-only path rather than
   creating or removing any worktree.

4. **Permissions:** nothing was denied. I ran no `atdd coach transition`, no `atdd coach approve`,
   no `gh issue create`, no `gh pr create`, no `--no-verify`, no force-push, no
   `atdd state migrate-layout`. No test was weakened, skipped, or `xfail`ed. All live-store reads
   were reads; the only backfill invocation was `dry_run=True`.

---

## Reproduction

The two probe scripts are in the session scratchpad (`probe.py`, `probe2.py`). Each builds its own
throwaway control root, real SQLite store, real `plan/` tree, and stub `gh`, then runs the real CLI
as a subprocess against both trees. Nothing outside its own `tmp` directory is written.
