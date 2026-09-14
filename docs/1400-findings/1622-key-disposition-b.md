# #1622 — worker 17 / part 4 — key dispositions

Read-only investigation. Store opened `mode=ro&immutable=1`. Repo:
`/Users/alecfokapu/Github/atdd/feat-projection-contract-diverged-from-store`.

Assigned two batches, five keys total. **None of the five is FIELD; none is EXTERNAL_REFS.**

## 1. Dispositions

| Key | Carriers (projectable / total) | Disposition |
|---|---|---|
| `created` | 68 / 72 | **STRIP at projection** — and stop the two live writers, or it returns |
| `id` | 68 / 72 | **STRIP at projection** — and stop the same two writers |
| `_recovery` | 515 / 767 | **STRIP at projection, do NOT drop from the store** — see §3 blocker |
| `merge_commit` | 50 / 262 | **DROP** — null on 50/50 projectable carriers |
| `closing_prs` | 50 / 262 | **DROP** — null on 49/50 projectable carriers |

Counts are from the live main-repo store. It drifted mid-session (798→803 objects,
544→549 projectable, mtime Jul 26 16:51); the five carrier counts above were stable
across every reading.

## 2. Evidence

### `created` and `id` — one finding, not two
They appear on **exactly the same 72 objects** (72 have both, 0 have only one). All 72
carry `_recovery` — they are carved recovery records whose shape descends from the legacy
`.atdd/manifest.yaml` session row.

**Live writers (these re-introduce the divergence after any fix):**
- `src/atdd/coach/commands/issue.py:2172` (`"id"`) and `:2178` (`"created"`), written to
  the bag at `:2183-2186` via `_store_create_work_item` — reachable today via
  `atdd coach reconcile`.
- `src/atdd/coach/commands/branch.py:322` (`"id"`) and `:329` (`"created"`), written at
  `:345-350` — reachable today via `atdd worktree create <N>` self-heal
  (`_backfill_from_github`, #775).
- `src/atdd/state/manifest_import.py:102` — wholesale legacy passthrough; historical origin.
- `src/atdd/train/persistence.py:568,571` (`upsert_issue`) — **no production caller**;
  referenced only by the Protocol decl `:104`, the impl `:543`, docs, plan, and two tests.

**Readers — one, and it is a dead read:**
- `src/atdd/train/persistence.py:755` (`id=str(session.get("id", session.get("issue_number", "")))`)
  and `:761` (`created=session.get("created", "")`), off `WorkItemReader.session_entry()`
  (`src/atdd/state/work_item_reader.py:193-204`).
- The *module* is core lifecycle (it feeds `materialize_evidence`, `persistence.py:589`).
  The *values* are never consulted: `Evidence(...)` at `persistence.py:614-628` carries
  neither, and repo-wide grep finds no `rec.id` / `rec.created` consumer. Both reads are
  defaulted; `id` falls back to `issue_number`.
- No reader in `src/atdd/coach/**`. `src/atdd/state/manifest_projection.py:44-45` names both
  in `_CANONICAL_SESSION_KEYS` for output ordering only, and that module **has no caller in
  `src/`** (`manifest_fallback.py:79` calls it "an outward write, never a read").

**Corroborating:** `src/atdd/state/manifest_migration.py:103` already classifies both as
drop-on-projection — `_DROPPED = frozenset({"id", "file", "created", "archived", ...})`,
commented "Manifest bookkeeping the projection has no field for". The sanctioned authoring
path never writes them: `src/atdd/planner/commands/author_publish.py:104-107` builds
`data = {title, type, branch, train, feature, body}`.

**`id` is provably redundant:** across all 68 projectable carriers,
`data["id"] == external_refs(github/issue).ref_value` — 68/68 match, 0 divergent, 0 without
a github ref. The single non-numeric value (`"1203-phase2"`) is on a `COMPLETE` object,
outside the projectable set.

### `_recovery`, `merge_commit`, `closing_prs` — no code touches them at all
Exhaustive search of `src/ tests/ docs/ plan/ tools/ e2e/` for all three names: **zero
occurrences.** `git log -S` over **all history** for `"_recovery"`, `"closing_prs"`,
`"merge_commit"`, `carved_original_rowid`, `audited-495`, `identity_note`,
`derived_slug_hint`: **all empty.** No writer, no reader, not even a test.

**The importer that wrote them does not exist in this tree and never did.** It was an
out-of-tree, uncommitted operator script run after the 2026-07-20 incident (~588 work_items
silently deleted; described in `src/atdd/state/reconcile.py` and
`src/atdd/state/projection.py:520-522` docstrings, but the repair tooling was never
committed). Only near-matches in tree are unrelated identifiers: `merge_commit_sha`
(`src/atdd/train/events.py:43`, `src/atdd/integrations/github/types.py:27`) and the method
name `get_closing_merge_commit` (`src/atdd/coach/github.py:529`).

`_recovery` shape — four forensic tiers, audit snapshot `2026-07-21T00:05:32Z`:
`audited-495` (495 total / 455 projectable, `confidence: high`), `github-repopulated`
(262 / 50, `authoritative: false`, `phase_confidence: low`), `reconciled-outside-audit`
(7 / 7, `needs_operator_review: true`), no-tier forensic-snapshot rows (3 / 3).

`merge_commit` and `closing_prs` are **one finding**: their carrier sets are set-identical
to each other *and* to the `_recovery.tier == "github-repopulated"` set — the same 262 uids.
Types: `merge_commit` str(200)/None(62); `closing_prs` list[int](202)/None(60). But 212 of
the 262 are `COMPLETE` and never projected, so within the **50 projectable** carriers
`merge_commit` is `None` **50/50** and `closing_prs` is `None` **49/50** (sole non-null
`[1575]`). They break the contract while carrying essentially no information.

Core lifecycle *does* consume the closing-merge-commit concept — the #1611 auto-phase
artifact gate at `src/atdd/coach/commands/issue.py:1164-1176` → `_closing_merge_sha` →
`src/atdd/coach/github.py:529-556` — but it shells out to `gh` **live on every call**,
memoized only in an in-process dict (`issue.py:1155-1162`). It never reads or writes the bag.
EXTERNAL_REFS fails criterion (b) on the writer axis: nothing writes them at all, bot or
otherwise. (If a future GitHub extension bot mirrors merge/PR state, `external_refs` is the
right home for *that* write; these 50 nulls are still DROP.)

## 3. Outranks my assignment — OUT OF SCOPE for my five keys, flagging anyway

**(a) BLOCKER — `_recovery` cannot be dropped from the store, only stripped at projection.**
`hydrate()` (`src/atdd/state/projection.py:557-561`) upserts the document's contents, and
`ObjectStore.upsert` is a **wholesale replace**: `ON CONFLICT(uid) DO UPDATE SET ...
data=excluded.data` (`src/atdd/state/store.py:128-130`), not a merge. CI's stated cycle is
"hydrate what the branch committed, then re-project it." So the moment the projector stops
emitting `_recovery`, the next hydrate **permanently deletes the forensic audit trail of a
data-loss incident from 515 live objects**, including the 7 stamped
`needs_operator_review: true`. Strip in `build_document`; do not write a store migration
that deletes it; fix hydrate's replace semantics or archive the 515 bags out-of-band first.

**(b) SCOPE CORRECTION — `additionalProperties` is necessary but nowhere near sufficient.**
`validate_document` also enforces the uid pattern and `required`
(`src/atdd/state/projection.py:319-331, 355-379`). In the live store:
**0 of 549 projectable uids match `^wi_[0-9A-HJKMNP-TV-Z]{26}$`** (397 are literal
`unverified:issue-<N>` placeholders the recovery script minted, self-described as
"non-authoritative placeholder keyed by issue number"), and **`owner_actor` — a required
field — is missing from all 549**. Dispositioning all 18 keys perfectly still leaves
`atdd state project` refusing every object. The issue's framing ("the contract sets
additionalProperties:false ... 18 keys it does not admit") reads as if the 18 keys are the
whole cause. They are not.

**(c) LIVE RE-INTRODUCERS.** `created`/`id` are not inert legacy: `atdd coach reconcile`
(`issue.py:2172,2178`) and `atdd worktree create` self-heal (`branch.py:322,329`) write them
today. A projector-only fix regresses on the next reconcile.

**(d) DEAD CODE adjacent to the fix.** `train/persistence.py::upsert_issue` has no production
caller, and `state/manifest_projection.py` has no caller in `src/` at all. Both are among the
few places that name these keys; deleting them removes the illusion of readership.

## 4. Confidence, and what would flip it

| Disposition | Conf. | Single piece of evidence that flips it |
|---|---|---|
| `created` STRIP | high | A ruling that "any read by a lifecycle *module*" counts — `persistence.py:761` then forces GROW. It could never become EXTERNAL_REFS: that bag is `lifecycle_readable: false`, which would break that very read. |
| `id` STRIP | high | Same ruling. Otherwise: a divergence between `data["id"]` and the github ref on any projectable object (I found 0/68). |
| `_recovery` STRIP-not-drop | high that no code reads it; **medium on the action** | The operator who ran the 2026-07-20 recovery declaring the record spent — that makes full DROP safe and moots the hydrate blocker. |
| `merge_commit` DROP | high | Confirmation that #1611 intends to *cache* merge SHAs in the store rather than re-derive live — that would give the key its first reader. |
| `closing_prs` DROP | high | Same. |

No files were modified; nothing was staged or committed.
