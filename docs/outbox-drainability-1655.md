# Outbox drainability — triage, decision, and the missing signal (#1655)

> Child of umbrella **#1652**. Siblings: **#1653** (rename uid grammar), **#1654**
> (revise title write). This document is the *recorded reason* half of #1655's
> done-when; the code half is the operator signal described in §5.
>
> Measured against the Control Root store
> `/Users/alecfokapu/Github/atdd/.atdd/state/state.sqlite` on **2026-07-29**.

## 0. Correcting the headline figure

The issue title says *21 stranded rows*. The table holds 21 rows, but the
**undrained** set is **19**:

| status | rows | ids |
|--------|------|-----|
| `pending` | 18 | 1, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21 |
| `failed`  | 1  | 4 |
| `sent`    | 2  | 2, 3 |

Rows 2 and 3 drained on 2026-07-09 00:52:25, back when
`src/atdd/integrations/github/state_sync.py` still hardcoded
`providers = {PROVIDER_NAME: GitHubSyncProvider()}`. Their existence is the proof
that this outbox *was* drainable once, and stopped being so when
`docs/ext40-phase2-core-seam-plan.md` decision 3 relocated the provider out of core.
That relocation is **correct and not the defect** — the plan names zero providers
"a supported state" (§Design decisions 3). The defect is that nothing said so out loud.

## 1. Operation split — this matters more than the count

| operation | pending | failed | ids |
|-----------|---------|--------|-----|
| `version_decided` | 9 | 1 | 12–19, 21 (pending); 4 (failed) |
| `create_issue`    | 7 | – | 1, 5, 7, 8, 9, 10, 20 |
| `update_issue`    | 2 | – | 6, 11 |

The three groups have three different root causes and three different dispositions.
Treating them as one "backlog to drain" is what makes this dangerous.

## 2. What a real drain would actually do today

`atdd.extension.github`'s provider
(`implementations/state_sync_provider/github_sync.py::GitHubSyncProvider.push`)
implements exactly three operations:

```python
if operation == "create_issue": ...
if operation == "add_label":    ...
if operation == "comment":      ...
raise ValueError(f"unknown github outbox operation: {operation!r}")
```

So installing the extension and running `atdd state sync --push` against this store
would:

- **create 7 GitHub issues**, of which 4 are byte-identical triplicates of one
  another (rows 7–10) and 1 duplicates an already-closed issue (row 1 → #1394);
- **raise `ValueError` on 11 rows** (2 × `update_issue`, 9 × `version_decided`),
  which `push_outbox` catches per-message, counts as `failed`, and leaves pending —
  so `atdd state sync --push` exits **1**, permanently;
- leave the backlog larger and noisier than it started.

Separately, `release_worker.drain_version_decided` — the worker that *does*
understand `version_decided` — iterates **every** pending row matching
`(operation, provider)`. Pointed at this store it would tag and publish
`4.7.0, 4.9.0, 4.10.0, 4.14.0, 4.16.0 ×4, 5.0.0` onto a line already at **v4.28.0**.

**Blind drain is destructive. Every row needs an individual disposition.**

## 3. Per-row triage

Legend: **DISCARD** = record a reason and close out; **BLOCKED** = still meaningful,
no shipped path can drain it.

### 3a. `create_issue` — 7 rows, all DISCARD

Each row is a durable retry enqueued when `author_publish.py`'s *direct* GitHub
projection failed. In every case the operator re-ran the authoring command instead of
draining the queue, so the row is a shadow of an attempt that was resolved (or
abandoned) elsewhere.

| id | date | title | disposition | evidence |
|----|------|-------|-------------|----------|
| 1 | 07-09 | Bind orphaned coach-verb-split E001-SMOKE-001 acceptance… | **DISCARD — superseded** | A retry created **#1394** at `2026-07-09T08:12:41Z`, title byte-identical. #1394 is CLOSED. Draining duplicates a closed issue. |
| 5 | 07-10 | Repoint null cross-wagon contract edges and ratchet registry coherence to strict | **DISCARD — abandoned** | No GitHub issue with this title (exact + fuzzy sweep over all 937 issues). No store object under slug `ratchet-registry-coherence-to-strict`. Untouched for 19 days. |
| 7 | 07-13 17:56:38 | Finish the engine migration: 74 convention-variant stubs… | **DISCARD — abandoned** | No GitHub issue exists. |
| 8 | 07-13 17:56:56 | *(byte-identical to 7)* | **DISCARD — duplicate of 7** | Four retries in 40 seconds. |
| 9 | 07-13 17:57:11 | *(byte-identical to 7)* | **DISCARD — duplicate of 7** | ” |
| 10 | 07-13 17:57:18 | *(byte-identical to 7)* | **DISCARD — duplicate of 7** | ” |
| 20 | 07-20 | Prune the observer convention and the observe-and-correct wagon (deferred from #1521) | **DISCARD — overtaken** | The prune already happened by another route: store objects `prune-observer-family`, `dangling-observer-convention-provenance`; GitHub **#1587** ("observer.convention.yaml dangles *after the observer prune*") is OPEN and postdates this row. |

### 3b. `update_issue` — 2 rows

| id | date | target | disposition | evidence |
|----|------|--------|-------------|----------|
| 6 | 07-12 | **#1361** (OPEN) | **BLOCKED — content still live** | Target issue is open; the queued body is still the intended content. But `update_issue` is not implemented by any shipped provider. Re-apply through the `atdd author issue --revise` path (**#1654**'s lane) rather than the outbox, then discard. |
| 11 | 07-14 | **#1477** (CLOSED 07-18) | **DISCARD — target terminal** | Issue closed 4 days after the update was queued; store object `unverified:issue-1477` is `COMPLETE`. Rewriting a completed issue's body has no reader. |

### 3c. `version_decided` — 10 rows, all DISCARD (and the most dangerous to drain)

These are **not** stale noise, and they are **not** meaningful to replay. They are
decisions that the store itself already retracted.

The `events` table shows every bump paired with a `change_class="SET"` reconcile that
walks the version back *down*:

```
 96  version_bumped {"change_class":"SET",   "from":"4.16.0","to":"4.15.0"}  2026-07-20 03:28:17
 95  version_bumped {"change_class":"MINOR", "from":"4.15.0","to":"4.16.0"}  2026-07-20 03:28:31   → outbox#18
 ...
104  version_bumped {"change_class":"MAJOR", "from":"4.16.0","to":"5.0.0", "pr":"1581"} 2026-07-21 → outbox#21
105  version_bumped {"change_class":"SET",   "from":"5.0.0", "to":"4.22.0"}  2026-07-22 07:49:48   ← 5.0.0 retracted
```

Rows **16, 17, 18, 19 all decide the same version 4.16.0**, four times, because each
cycle SET the store back to 4.15.0 and re-bumped. Row **21** decided 5.0.0 and was
retracted the next day.

**What published v4.23.0 … v4.28.0, then?** Not this outbox.
`.github/workflows/publish.yml` is the authoritative path, and it runs in CI against
a **fresh** store — `.gitignore:51` ignores `.atdd/state/state.sqlite*`, so the
Control Root store never reaches CI. Each publish job does:

```
LATEST=$(git describe --tags --abbrev=0)   # real released base
atdd state version set  "$BASE"            # reconcile — deliberately emits NO signal
atdd state version bump --class "$CLASS"   # decide → enqueues ONE fresh version_decided
… fetch release_worker … drain_version_decided(store)
```

So the authoritative decision is **re-derived in CI from the git tag every time**.
This local store reads `4.22.0` while the published line is `v4.28.0` simply because
nothing has run `set` locally since 2026-07-22.

| ids | decides | disposition | reason |
|-----|---------|-------------|--------|
| 4 (`failed`) | 3.149.1 | **DISCARD** | Five minor lines behind; already `failed`. |
| 12, 13, 14, 15 | 4.7.0, 4.9.0, 4.10.0, 4.14.0 | **DISCARD — superseded** | Each overtaken by the CI-published line. |
| 16, 17, 18, 19 | 4.16.0 ×4 | **DISCARD — superseded + triplicate** | Same version decided four times; SET-retracted each cycle. |
| 21 | 5.0.0 | **DISCARD — retracted** | Explicitly walked back by event 105 (`SET 5.0.0 → 4.22.0`) the following day. |

#### Consequent finding (recorded, not fixed — out of #1655's lane)

Every *local* `atdd state version bump` enqueues a durable, provider-routed publish
decision that **nothing local will ever drain**, because the real decision is re-made
in CI from the git tag. `CLAUDE.md::release.workflow` step 1 instructs operators to
run exactly that command. So 10 of the 19 stranded rows are **stranded by
construction**, and the release gate as written keeps producing them.

That is a `wagon:govern-lifecycle` concern (#1172 step 5 / E058's lane), not this
one. Per #1655's own Out-of-Scope precedent — *"record it and file it, do not do it
here"* — it is recorded here and should be filed against govern-lifecycle.

## 4. The `provider='github'` vs "provider-neutral" contradiction

Raised by the umbrella. **Resolution: the provider column is a routing key, and the
neutrality claim is scoped — but "configured" overstates what core actually offers.**

`src/atdd/state/version.py` is explicit and self-consistent about the scope of the
claim:

> Core owns the *number* and the *decision* only. … the operation name and payload
> name no provider, no PyPI, no "tag"/"publish", and core writes no git/github ref.
> … The outbox `provider` is a configured value (a keyword-only parameter defaulting
> to `"github"` …); *this* repo configures github, another stack passes its own.

Both halves check out: the payload really is `{"version": …, "change_class": …}` with
no provider, no tag, no publish; and `push_outbox` dispatches on `msg.provider` purely
as a `Mapping` key. So this is **not** a leak of GitHub semantics into core.

But the "configured" framing is aspirational. The one call site —
`src/atdd/state/cli.py:642` — is:

```python
new = ver.bump(conn, args.change_class, pr=args.pr)   # no provider=
```

`atdd state version bump` exposes no `--provider`, and nothing reads a provider from
config. So the keyword-only parameter is a **default that no shipped surface can
override**: every consumer, on every stack, inherits the routing key `"github"`.

Practical consequence, and the reason this belongs in *this* issue: **to drain a
version decision you must register a provider literally named `github`** — even on a
GitLab-only stack. That is what "register a provider" means here. The payload is
neutral; the routing key is provider-named by an unconfigurable default.

Recorded, not fixed: adding a real configuration surface is govern-lifecycle's call,
and changing the default would strand these rows harder, not less.

## 5. Decision — `atdd.extension.github` is **NOT** installed in this repo

Deliberate, and recorded here as the "deliberate, documented configuration" the
issue's done-when asks for.

1. **A drain today is destructive, not corrective** (§2): 7 issues created including
   4 duplicates, 11 rows hard-failing, `--push` exiting 1 forever.
2. **The GitHub write path is already live and is not the outbox.**
   `author_publish.py` projects to GitHub *synchronously*, store-first; the outbox is
   only its failure fallback. Installing the provider adds a **second, competing
   writer with no idempotency or dedup** — and §3a is the evidence that the two
   writers already disagree (every pending `create_issue` row is a shadow of an
   attempt the direct path resolved). Retiring the direct projection in favour of the
   seam is explicitly out of scope for #1655.
3. **The extension would not drain the majority of the backlog anyway** — 11 of 19
   rows are operations its provider does not implement.
4. **The release path already consumes the extension correctly, without installing
   it.** `publish.yml` fetches the release-worker at job time via `RELEASE_WORKER_REF`.
   Transient CI consumption is the right coupling for a publish side-effect; pinning
   it into `.atdd/substrate.lock.yaml` would give every local `atdd state sync --push`
   the power to tag and publish.

**Zero registered providers is therefore the correct configuration for this repo**,
exactly as `docs/ext40-phase2-core-seam-plan.md` anticipated. What was missing is not
a provider — it is the operator being *told*.

## 6. The actual defect, and the fix

> Silent accumulation is the actual defect. — #1655

Before this issue, the two commands an operator would reach for both reported the
undrainable state as **healthy**:

```
$ atdd state providers
no SyncProvider is registered — core runs provider-free (spec §8.1)     # exit 0

$ atdd state sync
outbox: 18 pending (pass --push to send via registered providers)       # exit 0
```

The first never mentions that 19 rows are queued behind that reassuring sentence. The
second names a remedy — "pass `--push`" — that cannot work, because no registered
provider can accept any of those rows.

The fix (see the accompanying code change) makes the *conjunction* — non-empty outbox
**and** no provider that can drain it — a first-class, named condition that both
commands report loudly, and gives the backlog a disposition path that records a
reason instead of deleting rows.

## 7. Proposed operator step — NOT executed

Both sibling workers (#1653, #1654) are measuring the same Control Root store
concurrently. Per the umbrella's instruction, dispositioning the rows is proposed
here, **not performed**:

```sh
# review first — prints every row with its computed drainability
atdd state outbox list

# then, per §3, discard with the recorded reason (one row at a time, by design)
atdd state outbox discard 1  --reason "superseded by #1394 (see docs/outbox-drainability-1655.md §3a)"
atdd state outbox discard 5  --reason "abandoned; never re-attempted (§3a)"
atdd state outbox discard 7  --reason "abandoned; never re-attempted (§3a)"
atdd state outbox discard 8  --reason "duplicate of outbox#7 (§3a)"
atdd state outbox discard 9  --reason "duplicate of outbox#7 (§3a)"
atdd state outbox discard 10 --reason "duplicate of outbox#7 (§3a)"
atdd state outbox discard 11 --reason "target #1477 closed + COMPLETE (§3b)"
atdd state outbox discard 20 --reason "overtaken; prune landed via #1587 (§3a)"
atdd state outbox discard 4  --reason "version 3.149.1 superseded by v4.28.0 (§3c)"
atdd state outbox discard 12 --reason "version 4.7.0 superseded by v4.28.0 (§3c)"
atdd state outbox discard 13 --reason "version 4.9.0 superseded by v4.28.0 (§3c)"
atdd state outbox discard 14 --reason "version 4.10.0 superseded by v4.28.0 (§3c)"
atdd state outbox discard 15 --reason "version 4.14.0 superseded by v4.28.0 (§3c)"
atdd state outbox discard 16 --reason "version 4.16.0 superseded + triplicate (§3c)"
atdd state outbox discard 17 --reason "version 4.16.0 superseded + triplicate (§3c)"
atdd state outbox discard 18 --reason "version 4.16.0 superseded + triplicate (§3c)"
atdd state outbox discard 19 --reason "version 4.16.0 superseded + triplicate (§3c)"
atdd state outbox discard 21 --reason "version 5.0.0 retracted by SET → 4.22.0 (§3c)"
```

Row **6** is deliberately left pending: it is the one row whose content is still
live (§3b). It should be re-applied to #1361 through #1654's revise path and
discarded then — leaving a bounded, explained remainder of exactly one row, which is
what "bounded with a reason" means in the issue's own success criteria.

After that, `atdd state outbox check` reports one undrainable row instead of 19, and
says why.
