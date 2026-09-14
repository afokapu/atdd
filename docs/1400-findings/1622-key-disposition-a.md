# #1622 — key dispositions (worker w17-p3)

Read-only investigation. Repo: `feat-projection-contract-diverged-from-store`.
Store: `/Users/alecfokapu/Github/atdd/.atdd/state/state.sqlite` (`mode=ro&immutable=1`).

**Vocabulary note.** I reached dispositions in the brief's FIELD / EXTERNAL_REFS / DROP terms.
Mapping to GROW/STRIP/DROP is exact for two of three: FIELD = GROW, DROP = DROP.
EXTERNAL_REFS is *not* "STRIP at projection" — it means relocate into the contract's
`external_refs` object, which **is still projected**. Flagged inline rather than mis-mapped.

**Snapshot caveat.** The store was being written *during* the investigation: `work_item`
798 → 803, projectable (non-`COMPLETE`) 544 → 549 between two connections. All figures are
from a single connection. The seven carrier counts below were stable across both snapshots;
only the denominator moved.

## 1. Assignment + disposition

| Key | Projectable carriers | Disposition |
|---|---|---|
| `type` | 170 | **GROW** to a real field (`["string","null"]`) |
| `archetype` | 50 | **DROP** |
| `archetypes` | 1 | **DROP** (alt: EXTERNAL_REFS — real choice, see §2) |
| `github_state` | 512 | **DROP** |
| `labels` | 512 | **DROP** |
| `issue_number` | 512 | **EXTERNAL_REFS** — relocate, still projected. NOT drop. |
| `label_phase` | 50 | **DROP** |

## 2. Evidence

### `type` — GROW (170 carriers, 393 total)
Live writers: `planner/commands/author_publish.py:105` (`data={"type": issue_type,…}` →
`create_work_item` at `:123`/`:178`/`:213`); `state/work_item_writer.py:183`
(`updates["type"]=issue_type` in `revise_work_item_issue`, upserted `:191`);
`coach/commands/issue.py:2172` (reconcile backfill, hard-coded `"implementation"`).

**Core-lifecycle readers — this is what forces GROW:**
- `coach/commands/branch.py:403` — `entry.get("type","implementation")` → `TYPE_TO_PREFIX` →
  `branch_name = f"{prefix}/{slug}"` and the worktree dir. `atdd worktree create`.
- `coach/commands/branch.py:602` — same derivation computes the path handed to
  `git worktree remove`.
Both read through `branch.py:46 _store_session_entry` → `state/work_item_reader.py:193
session_entry` (`{**obj.data,…}`). Under `src/atdd/coach/**`, so `field-ownership.yaml`'s
`external_refs: lifecycle_readable: false` forbids EXTERNAL_REFS.
Reporting-only readers: `coach/commands/pr.py:642` (PR title), `pr.py:484` (PR body row).

Store: `str` (148 projectable) + **`null` (22 projectable)** → must be `["string","null"]`.
17 objects (4 projectable) hold scraped-markdown garbage, e.g. `` "cleanup` (regression-fix)" ``,
one 140 chars. All on `unverified:issue-*` uids.

### `archetype` — DROP (50 carriers, 262 total)
**Zero writers, zero readers — including tests.** Whole-repo whole-word search: every hit is
the *rule-ID* archetype concept (`cli.py:1713,2656`; `coach/handlers/validator_dispatch.py:136-160`;
`coach/utils/rule_binding.py:841`; `coach/utils/rule_validator_resolver.py:20-23`;
`planner/validators/_theme_taxonomy.py:62,130`; `enforce/conventions.py:327`). None is a
work_item data key. 262/262 carriers are `unverified:issue-*`; 0 of 165 non-recovery objects.
Vocabulary (`be`/`fe`/`wmbt`/`coach`) = the #1051-decommissioned Projects v2 board field
(`coach/commands/issue.py:56-80 ARCHETYPE_GATES`). Singular misspelling of the live plural.
28 of 50 projectable values are `null`.

### `archetypes` — DROP (1 carrier)
Live writer chain: `cli.py:804` (`--archetypes`) → `cli.py:2313` → `coach/commands/issue.py:1582
IssueManager.update` → `:1630` → `:1708` → `:1714` → `:381` → `:347 _store_update_fields` →
`objects.upsert` at `:367`. Sole reader: `coach/commands/pr.py:490-491`, one PR-body table row.
No lifecycle reader. n=1 (`git-hook-interpreter-cannot-import-atdd-local-gate-inert`, `"coach"`, a
`str` despite the plural name). **Genuine fork:** DROP requires also retiring `cli.py:804` and
`pr.py:490`; EXTERNAL_REFS keeps `atdd update --archetypes` working through the projection.

### `github_state` — DROP (512 carriers, 764 total)
`rg -w 'github_state'` repo-wide, incl. `tests/`, `contracts/`, `.atdd/`, hidden: **exit 1,
zero occurrences.** No writer, no reader, no test. `str` only: `CLOSED` 581 / `OPEN` 183.
Already self-contradicting: 344 of 512 projectable carriers say `CLOSED` on a non-`COMPLETE`
item; 15 say `OPEN` on a `COMPLETE` one.

### `labels` — DROP (512 carriers, 764 total)
No data-bag writer. `author_publish.py:201` writes `labels` into an **outbox payload**
(`store.sync.enqueue_outbox`), not `data`. No data-bag reader: all ~20 `labels` reads take a
**live GitHub payload** — `coach/store_mirror_gate.py:128,170`; `coach/commands/pr.py:211,494`;
`coach/commands/issue.py:667,815,886,947,1764,2168`; `coach/commands/issue_lifecycle.py:402,475,529`;
`coach/commands/branch.py:312`; `coach/commands/issue_reconcile_state.py:428`.
**Shape mismatch proves they are not the same source:** GitHub returns `[{"name":…}]` (every
reader does `l["name"]`), the store bag holds bare strings `["atdd-issue","atdd:INIT"]`.
**278 of 764 embed an `atdd:<PHASE>` that contradicts `objects.state`** (461 agree, 25 none).

### `issue_number` — EXTERNAL_REFS (512 carriers, 764 total)
Live writer: `coach/commands/issue.py:2174` → `:2183` → `:761 create_work_item` — writes the
number **twice**, into the data bag *and* the `external_refs` table. Legacy:
`state/manifest_import.py:103,109`. (`work_item_writer.py:197` is an *event payload*, not a writer.)

Authoritative resolution is **external_refs → uid**, never the bag:
`state/work_item_reader.py:110-121 get()`; `:173-184 issue_number_for_slug()`;
`:220-229 all_work_items()` which **overwrites** any bag value (`entry["issue_number"]=by_uid[obj.uid]`).
Two bag-shaped reads exist but are defensively overridden: `train/persistence.py:757`, whose
caller `:541` does `entry.setdefault("issue_number", n)` and whose docstring `:530-531` states
*"store `data` bags do not carry it"*; and `coach/commands/issue.py:2235-2237`, reading the
external_refs-derived value. **No core lifecycle reads the bag** → `lifecycle_readable:false` is met.

Store: `int`. **AGREE=763, DISAGREE=0** vs `external_refs`. 858 github/issue refs, one per
`object_uid`, zero dupes, zero orphans. 39 refs-only (post-recovery authored — matches 39
`work_item_authored` events). **1 data-only**: `my-slug`/RED/`42`, a fixture-shaped uid.

**Why not DROP:** `hydrate()` (`state/projection.py:549-566`) upserts **only** `store.objects`
— it never writes the `external_refs` table, and nothing else projects that table (only the
`data["external_refs"]` *field* at `projection.py:93,403`). The table does **not** survive
project → hydrate. Drop it from the bag and the committed projection carries *no* GitHub
linkage at all. Relocating into `external_refs` keeps it projected, provider-owned, and
lifecycle-unreadable. **Prerequisite:** backfill an `external_refs` row for `my-slug` first.

### `label_phase` — DROP (50 carriers, 262 total)
Appears in code but **never as a data key** — always a local/dataclass field fed from a *live*
GitHub read: `coach/commands/auto_phase.py:125` (`resolution.get("phase_label")`, where
`resolution` = `pr.py:272-284 resolve_linked_issue`, a live 4-strategy `gh` cascade), `:59`,
`:132-175`; `coach/commands/issue_reconcile_state.py:111,160,175,344`;
`issue_reconcile_state_report.py:91`. `auto_phase.py:132-147` *is* core lifecycle (raises
`action="divergence"`) but compares a value fetched live at decision time — reading a frozen
store copy there would defeat the check. 262/262 carriers are `unverified:issue-*`.
**40 of 241 non-null values contradict `objects.state`**, all store-`COMPLETE` vs a lower label.

## 3. Outranks my assignment — OUT OF SCOPE for my keys, escalating

1. **`atdd coach reconcile` is a live re-introducer.** `coach/commands/issue.py:2172-2183`
   still writes `id`, `file`, `issue_number`, `type`, `created`, `archived` into the data bag on
   every backfill. **`id`, `file`, `created`, `archived` are other workers' keys** — but whatever
   they decide, that one dict re-opens the divergence on the next reconcile run. Single choke
   point; needs one coordinated trim, not four independent ones.
2. **An out-of-tree importer produced most of the divergence.** All 764/262 carriers of the
   GitHub cluster, plus `archetype` and the malformed `type` values, come from the 2026-07-21
   carve-recovery cohort (`_recovery` bag; `"identity_note": "issue_number is the durable
   authoritative identity; uid is re-bindable"`). **It is not in this tree.** Zero of the 36
   post-recovery objects carry any of these keys. If it is not retired, cleanup regresses.
   Out of scope for my keys; blocks the whole issue.
3. **Three keys are stale duplicate phase state.** `labels` contradicts `objects.state` on 278
   objects, `label_phase` on 40, `github_state` on 344 projectable carriers. Promoting any to a
   field would commit the #1338/#1452 label drift into the git artifact as authoritative bytes.
4. **`external_refs` table ≠ `external_refs` field.** Currently discoverable only by reading
   `hydrate`'s body (`projection.py:549-566`). Worth stating in the projection spec regardless
   of #1622's outcome. Scope correction, not a key disposition.
5. **`type` vocabulary is already forked** — `coach/commands/issue_prefixes.py:16-25 TYPE_TO_PREFIX`
   = `{implementation,migration,refactor,analysis,planning,cleanup,tracking}` vs
   `planner/schemas/author/issue.schema.json` `type.enum` =
   `{implementation,bug,feature,refactor,docs,chore,devops}`. `bug`/`feature` (23 projectable)
   fall through to the `"feat"` default. Any enum on the grown field needs this reconciled
   **and** the 4 malformed projectable values cleaned, or projection still refuses.
6. **Store is live-written.** Any validator asserting an exact projectable count will flake.
7. **Fixture-shaped uids in the real store:** `my-slug`, `the-slug`, `t`, `x`. Probably want
   tombstoning; not mine to call.

## 4. Confidence + the single flipper

| Key | Conf. | Evidence that would flip it |
|---|---|---|
| `type` → GROW | high | A decision to delete `atdd worktree create`'s type→prefix derivation (`branch.py:403,602`). Nothing else demotes it. |
| `archetype` → DROP | high | Any site reading `data["archetype"]` — I found none, incl. tests. |
| `archetypes` → DROP | **medium** | Evidence operators still run `atdd update --archetypes` (shell history, CI logs, `events` table) → flips to EXTERNAL_REFS. At n=1 there is no usage signal either way. |
| `github_state` → DROP | high | Any occurrence of the string anywhere (currently zero repo-wide). |
| `labels` → DROP | high | A commissioned provider bot to keep them fresh + a consumer. Today: neither. |
| `issue_number` → EXTERNAL_REFS | **med-high** | A ruling that the committed projection is *only* the CI round-trip check and never a store-recovery source → DROP becomes correct. `hydrate`'s docstring ("the read half of the CI guarantee") argues that way; the schema's "Authoritative for shared project state" argues the other. **Not settleable read-only — owner of the projection spec must call it.** |
| `label_phase` → DROP | high | A site reading `data["label_phase"]` rather than the live label. |
