# #1622 key dispositions — worker W17 (batches: archived/worktree_path, branch/wagon/feature/worktree)

Read-only investigation. Store read at `/Users/alecfokapu/Github/atdd/.atdd/state/state.sqlite` (`mode=ro&immutable=1`).
Code from `/Users/alecfokapu/Github/atdd/feat-projection-contract-diverged-from-store`.
`/tests/` and `test_*` excluded from writer/reader lists.

## 1. Dispositions

| key | carriers (projectable / total) | disposition |
|---|---|---|
| `archived` | **0** projectable / 18 total (all COMPLETE) | **DROP** |
| `worktree_path` | 25 / 35 | **DROP** |
| `worktree` | 51 / 263 (only **1** non-null) | **STRIP at projection** (cannot be grown — see §3) |
| `branch` | 115 / 339 (48 non-null) | **STRIP at projection** |
| `wagon` | 55 / 267 (8 non-null) | **GROW to a real field** |
| `feature` | 96 / 311 (33 non-null) | **GROW to a real field** |

Projectable = non-`COMPLETE` (`ARCHIVED_PHASES = ("COMPLETE",)`, `src/atdd/state/projection.py:70`). 549 projectable at time of read.

**Counts drifted mid-session: store went 798 -> 803 work_items.** My `branch` (115) and `feature` (96) exceed the brief's 109/91. Re-measure before quoting.

## 2. Evidence

### `archived` — DROP
- Writers: `src/atdd/coach/commands/issue.py:967` (live, on archive); `src/atdd/train/persistence.py:572`; null-seeds at `src/atdd/coach/commands/issue.py:2179` and `src/atdd/coach/commands/branch.py:330`.
- Reader: **exactly one** — `src/atdd/train/persistence.py:762` `session.get("archived")` in `_record_from_session`, fed by `get_issue()` (`persistence.py:530-541`) via `WorkItemReader.session_entry`. Value lands in `IssueRecord.archived` (`persistence.py:73`) and `rg '\.archived\b'` finds **no consumer** except the write-back at `:572`. Pure round trip.
- Not read by `src/atdd/state/work_item_reader.py` (named accessors are train/branch/wagon/feature only, `:44-48`) nor anywhere in `src/atdd/coach/**`.
- **0 of 549 projectable objects carry it.** It blocks nothing.
- Consequence: `IssueRecord.archived` becomes permanently `None`. Nothing reads it, so lossless — but delete the field or mark it vestigial.

### `worktree_path` — DROP
- Writer: **one**, `src/atdd/coach/commands/branch.py:186` `_record_binding_in_store` (called `:512`).
- Readers: **none**. Three near-misses ruled out:
  - `src/atdd/coach/commands/branch.py:554` docstring claims `list_worktrees` reads `data.worktree_path`; impl at `:563-572` reads **only** `data.branch`. **Stale docstring.**
  - `src/atdd/coach/commands/issue.py:303-333` `branch_is_registered` (the #1270 gate, named as the consumer in `plan/drive_state_machine/E007.yaml`) resolves by **slug uid**, reads neither key.
  - `src/atdd/state/cli.py:708` reads the `SessionParticipation` dataclass sourced from a **relationship** bag (`src/atdd/state/agent_session.py:211` write / `:337` read) — different surface; 0 `agent_session` objects carry it.
- All 35 values are absolute host paths under `/Users/alecfokapu/`.

### `worktree` — STRIP (contract-illegal as a field)
- Writers into a work_item bag: **none found**. `src/atdd/runtime/worktree.py:185,208,222` and `src/atdd/coach/utils/ff_default_branch.py:120` put `"worktree"` in log `extra=` dicts only. The 51 carriers are manifest-import residue (`src/atdd/state/manifest_import.py:106`).
- Readers: **none**, test or non-test.
- **Growing a field would not fix it.** `build_documents` (`src/atdd/state/projection.py:445-449`) runs `assert_deterministic` over the *whole* document **before** `validate_document`. `_HOST_PATH_RE` (`projection.py:186`) matches `/Users/`. The single non-null projectable value is `REFACTOR smoke-token-missing-from-acceptance-urn-enum -> '/Users/alecfokapu/Github/atdd/feat-smoke-token-missing-from-acceptance-urn-enum'`. Per the docstring, one leak leaves the **whole** projection unwritten. Schema-growing it changes nothing.

### `branch` — STRIP
- Writer: **one**, `src/atdd/coach/commands/branch.py:186`.
- Readers (2, **neither a decision module**):
  - `src/atdd/state/agent_session.py:308` `_work_item_for_branch`, used by `capture_post_commit` (`:272`). `state.agent_session` is **absent** from `hot_path.DECISION_MODULES` (`src/atdd/state/hot_path.py:83-97`); its failure path is `return False` in a never-raise `try/except`.
  - `src/atdd/coach/commands/branch.py:572` — `atdd worktree list` display only.
- `WorkItemReader.branch()` (`work_item_reader.py:133`) has **test-only callers**. (`issue_lifecycle.py:172`, `cli.py:2324/2359` call `BranchManager.branch()` — a different method that creates a worktree.)
- **Regenerates locally**: written by `atdd worktree create` on the machine that needs it, so hydrate-loss is recoverable. 58% of carriers are null.

### `wagon` — GROW
- Writers: `src/atdd/state/work_item_writer.py:63` `create_work_item` (reached from `atdd author issue` and `src/atdd/coach/commands/issue.py:728`). Authored at creation, never recomputed.
- Readers, **both declared decision modules**:
  - `src/atdd/state/work_item_reader.py:138` `wagon()` -> `src/atdd/coach/commands/issue_graph.py:42` -> `:333`.
  - `src/atdd/state/work_item_reader.py:143` `issue_wagon_map()` -> `src/atdd/coach/runtime/graph.py:85` -> `:113` `graph_issue_deps` -> **`src/atdd/coach/commands/wave_planning.py:143`** (wave ordering) and **`src/atdd/coach/commands/merge_cascade_topology.py:169`** (merge ordering).
  - `src/atdd/state/hot_path.py:93,94` lists both in `DECISION_MODULES`, annotated "the gate graph" / "issue -> wagon resolution, which gates read".
- **Not derivable from `feature`**: of 39 objects carrying both, the `feature:<wagon>:<x>` middle segment matches `wagon` in only **4**; 35 disagree (bare slugs like `progressive-universality`, `govern-lifecycle/cli-dispatch`).
- **Live, not stale**: all 8 projectable non-null wagons resolve to a real `plan/<wagon>/_<wagon>.yaml` (govern-lifecycle x4, validate-conventions x2, define-plans x1).
- Determinism: 0 offending values.

### `feature` — GROW
- Writers: same `create_work_item` path; also emitted into every authored issue body Metadata table (`src/atdd/planner/commands/author_issue.py:140,161`).
- Readers: `work_item_reader.py:167` `feature()` has **test-only callers**. No live bag read. (The many `feature` hits in `coach/utils/graph/`, `planner/`, validators are the plan-graph URN concept — **name collision**, not the work_item bag. State this in the plan or the next reader over-counts.)
- Grow anyway: authored content with **no regeneration path** (unlike `branch`); the declared successor in `Wagon -> Train + Feature`; and its sibling `train` is already a field (`.atdd/policy/field-ownership.yaml`, `writer: core_train_ops`).
- Type it `["string","null"]` with **no pattern** — data is heterogeneous (full URNs, bare slugs, one prose value `'n/a — this umbrella spans train 0008-unify-urn-grammar, not a single feature'`). A URN pattern would refuse the whole set.

## 3. Outranks my assignment (OUT OF SCOPE for my keys — escalate)

1. **`src/atdd/cli.py:129` is wrong operator-facing text.** It tells operators the store carries "a `wagon` field that the store no longer carries (Wagon -> Train + Feature)". The store carries `wagon` on **267 objects**, and **two `DECISION_MODULES` read it**. `atdd coach sync-wmbts` was removed (#1477) on that premise. This sentence is how a live gate-graph field gets deleted by someone who believed it. Fix independent of #1622.

2. **The projection is a lossy round trip, not a view.** `src/atdd/state/projection.py:549` `hydrate()` rebuilds the store from committed YAML with "zero sync providers registered and against no committed SQLite store". A stripped key is **absent from the CI-hydrated store and from every peer**, not merely absent from the doc. Any #1622 plan phrased as "the store still has it" is wrong.

3. **A strip mechanism must be built regardless.** `build_document` (`projection.py:393`) is `dict(obj.data)` verbatim and its docstring asserts "nothing is silently dropped on the way out". `worktree` cannot be admitted as a field (§2), so the filter is mandatory. This removes the "stay minimal is free" argument and makes #1622 a per-key call, not a policy toggle. **Update that docstring and log which keys were dropped** — a stripped projection otherwise reads as a complete one.

4. **STRIP-all-four fails silently, which is the worst shape.** Both `wagon` readers are wrapped in `except: return {}` (`coach/runtime/graph.py:86-87`, `coach/commands/issue_graph.py:44-45`). Losing `wagon` gives every issue an empty dep set -> `wave_planning` orders everything into wave 1, `merge_cascade_topology` loses transitive ordering, **no error raised**.

5. **`check_canonicality` is safe either way** — `project(hydrate(committed)) == committed` holds under stripping (strip once, hydrated store never carries the key, re-projection strips nothing). No fixpoint problem. Not a blocker.

6. **Growing costs mandatory ownership entries.** `src/atdd/state/ownership.py:368` `check_coverage` refuses any schema field left unowned. `wagon`/`feature` are authored-at-creation -> `writer: core_authoring`, `rule: mutable` (mirrors `slug`); if `wagon` warrants conflict protection for the gate graph, `core_train_ops` / `conflict-unless-same-digest` mirrors `train`.

7. **`manifest_migration._DROPPED` (`src/atdd/state/manifest_migration.py:103-104`) lists `archived`, `worktree_path`, `branch`, `worktree`.** Per the brief this only filters manifest->projection output in `build_document()`, never the store — so it is **not** authority for batch 2. It *is* corroborating for batch 1 (`archived`, `worktree_path`), where the live store writers (`issue.py:967`, `persistence.py:572`, `branch.py:186`) simply never stopped writing keys the migration already disowned. Arguably that, not the contract, is the batch-1 defect.

8. **Stale docstring + stranded spec, `worktree_path`**: `coach/commands/branch.py:554` claims a read that does not exist; `plan/drive_state_machine/E007.yaml:27,68` assert `data.worktree_path` is written for a consumer that was then built to resolve by slug instead. Fix the docstring in the same change or the wrong belief gets re-derived.

## 4. Confidence, and the single thing that flips each

| key | disposition | confidence | flips on |
|---|---|---|---|
| `archived` | DROP | **high** | an out-of-tree extension reading `session_entry()["archived"]` |
| `worktree_path` | DROP | **high** (no reader) / medium on intent | operator confirming `atdd worktree list` or the pre-commit gate should be re-pointed at `data.worktree_path` — even then it should not be a projection field (host path) |
| `worktree` | STRIP | **high** | nothing realistic; the I1 host-path refusal is mechanical |
| `branch` | STRIP | **medium-high** | confirmation that `capture_post_commit` IS expected to work against a freshly hydrated CI store (would force GROW) |
| `wagon` | GROW | **high** | the two `DECISION_MODULES` readers being deleted first — then it is a normal field removal, not a strip |
| `feature` | GROW | **medium-high** | operator confirming `feature` on work items is dead metadata rather than the `Wagon -> Train + Feature` landing zone. **Worth one direct question.** |
