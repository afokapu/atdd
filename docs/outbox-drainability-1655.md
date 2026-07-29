# Outbox drainability — triage, decision, and the missing signal (#1655)

> Child of umbrella **#1652**. Siblings: **#1653** (rename uid grammar), **#1654**
> (revise title write). This document is the *recorded reason* half of #1655's
> done-when; the code half is the operator signal described in §5.
>
> Measured against the Control Root store
> `/Users/alecfokapu/Github/atdd/.atdd/state/state.sqlite` on **2026-07-29**.

## 0. Correcting the headline figure — and how to state it

The issue title says *21 stranded rows*. Two things are wrong with that, and the
second matters more than the first.

**First**, 21 is the row *total*, not the undrained set. At the first measurement
(`2026-07-29T~07:00Z`) that was 18 pending + 1 failed = **19 undrained**, with 2
`sent`.

**Second — and this is the part to carry forward — any bare count is wrong by the
time it is read.** This backlog is not a historical artifact; it grows during normal
work. Measured counts, each anchored:

| measured (UTC) | total | pending | failed | sent | undrained |
|---|---|---|---|---|---|
| 2026-07-29 ~07:00 | 21 | 18 | 1 | 2 | **19** |
| 2026-07-29 10:16 | 26 | 23 | 1 | 2 | **24** |

**Five rows were added during the single session that triaged this issue** (ids
22–26): two `version_decided` from local version bumps, and three `update_issue`
from workers dogfooding the repaired revise path. That is a ~26% growth in the
backlog in about three hours of ordinary work, with no operator ever being told.

So: **state any count as of a timestamp, with the method.** The method here is

```sh
atdd state outbox check --json     # anchored: emits measured_at alongside the counts
```

which is one of the reasons the `check` verb exists. A count without a timestamp in
this table will be wrong before anyone acts on it — as mine was, twice.

Status split at the first measurement:

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

**What published v4.23.0 … v4.28.0, then?** Not this outbox — and the answer is
*not* "a clean CI pipeline" either. Named and verified:

**`.github/workflows/publish.yml` → `atdd.extension.github`'s
`release_worker.drain_version_decided`, running in CI against a fresh store.**
`.gitignore:51` ignores `.atdd/state/state.sqlite*`, so the Control Root store never
reaches CI. Verification, not inference:

- every tag `v4.23.0` / `v4.26.0` / `v4.28.0` is an annotated tag whose tagger is
  **`atdd-release-bot`** — the identity `publish.yml:90` configures;
- PyPI genuinely holds `4.23.0 … 4.28.0` (`info.version == 4.28.0`);
- `real_publish` (extension) orders side-effects **tag → push → build → twine upload
  → `gh release create`**.

But **every recent publish run is red.** `gh run list --workflow=publish.yml` shows
failure on 2026-07-23, ×6 on 07-25, and 07-29. The 07-29 run (v4.28.0) failed like
this:

```
Draining version_decided for version 4.28.0 (dry_run=false)...
release publish failed; leaving outbox message pending
drain reported 1 failure(s): ["outbox#N v4.28.0: publish of v4.28.0 failed:
  ['gh','release','create','v4.28.0','--verify-tag','--generate-notes',...] exited 4:
  gh: To use GitHub CLI in a GitHub Actions workflow, set the GH_TOKEN environment variable."]
```

So the tag was pushed and PyPI **was** uploaded; only the trailing, cosmetic
GitHub-Release step failed, for want of `GH_TOKEN` in the workflow env. Because
`real_publish` raises after a *successful* upload, the worker's documented contract
("publish raises → leave the message pending, never a fake green") misfires in the
one direction it cannot detect: the completion marker (`external_ref`) is never
written, so **CI re-drains and re-publishes on every subsequent run**, saved from
visible damage only by `twine upload --skip-existing` and the
`git describe --exact-match HEAD` skip.

Consequence for this issue: the stranding is **not only local**. Each red run also
leaves its own freshly-enqueued `version_decided` row pending in CI's ephemeral
store, which is then destroyed with the runner.

Two follow-ups, both outside #1655's lane and neither fixed here: a one-line
`GH_TOKEN:` addition to `publish.yml`'s drain step (core, `wagon:govern-lifecycle`),
and `real_publish` distinguishing a failed *upload* from a failed *announcement*
(extensions repo — explicitly out of scope per #1655).

Each publish job does:

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
| 22 | 4.23.0 | **DISCARD — born stranded** | See below. |

#### Row 22 — the defect reproducing itself, live

Row 22 did not exist when this triage began. It was enqueued at
**2026-07-29 08:34:55**, *during* the work on #1655, by a local
`atdd state version bump --class MINOR` against a store still reading `4.22.0`. It
therefore decided **4.23.0** — a version tagged on 2026-07-23 and on PyPI for six
days.

It is the clearest possible statement of the defect: the row was **unroutable the
instant it was written**, decided a version that had already shipped, and nothing
told anyone. It also moves the live count to **20 undrained** (19 pending + 1
failed) and confirms the accumulation is ongoing, not historical.

#### Rows 23–26 — the same defect, four more times, in one session

| id | op | queued (UTC) | what it is |
|----|----|--------------|------------|
| 23 | `version_decided` | 07-29 08:49 | decided **4.24.0** from a store reading 4.23.0 — same pattern as row 22 |
| 24 | `update_issue` | 07-29 08:54 | a worker's revise of the #1654 issue body |
| 25 | `update_issue` | 07-29 09:10 | a worker's revise of **#1478** |
| 26 | `update_issue` | 07-29 09:22 | a worker's revise of **#1635** |

Rows 24–26 are the sharper finding. They were produced by workers *correctly* using
the repaired `atdd author issue --revise` path — the sanctioned write path, behaving
as designed. Its GitHub projection failed, so each fell back to the outbox, which is
exactly the durable-retry design. And `update_issue` is an operation **no shipped
provider implements**, so all three were unroutable and undeliverable the instant
they were written.

The sanctioned write path, working as intended, feeds a queue that cannot deliver
what it receives. That is the whole defect in one sentence, and it is why the signal
had to go on the surfaces operators already run rather than into a new report nobody
opens.

#### A version bump is unattributable — the same silent shape, on the release path

Recorded, not fixed. This is in scope because rows 22 and 23 *are* these two bumps,
and because it is the identical failure mode: a write nobody is told about.

Measured on the store, `2026-07-29`:

| event | payload | queued |
|---|---|---|
| 254 | `{"change_class":"MINOR","from":"4.22.0","pr":null,"to":"4.23.0"}` | outbox#22 |
| 256 | `{"change_class":"MINOR","from":"4.23.0","pr":null,"to":"4.24.0"}` | outbox#23 |

The `version_bumped` payload is written at `src/atdd/state/version.py:315-319` and its
schema is `{from, to, change_class, pr}`. **There is no actor field**, and `pr` is
`null` for both. So the store records that the release version moved twice during one
session and cannot say who moved it. A release-critical write with no attribution is
unauditable by construction — the same shape as the outbox that accumulated for
twenty days without telling anyone, relocated onto the release path.

Two related claims were checked and **could not be substantiated**, so they are
recorded as open rather than as findings:

- A `permissions.deny` block naming `Bash(atdd coach transition*)` /
  `Bash(atdd state version*)` was reported as the mechanism holding these hops.
  Neither pattern appears in `.claude/settings.local.json` (its `deny` list is
  empty) nor in `~/.claude/settings.json` — which in fact **allow**-lists
  `Bash(atdd coach transition:*)`. The denials observed in this session came from
  the harness's interactive prompt, not from a configured rule.
- Consequently the "the guardrail leaks through the `python -m` invocation form"
  claim cannot be confirmed here: there is no matching deny rule for an alternate
  invocation form to evade.

What survives verification, and what matters for this issue, is the first paragraph:
the bumps happened, they each enqueued a stranded row, and **nothing records who did
it**.

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

## 4b. Feature binding — the declared URN did not exist

#1655's Metadata declared `Feature: feature:bind-substrate-runtime:state-sync-providers`.
**That feature URN exists nowhere** in `plan/` or `contracts/` — the only feature in
that wagon is `feature:bind-substrate-runtime:substrate-binding`, which is about
binding locked extension packages to gating capabilities, a different concern.

This is not cosmetic. `smoke_obligation._feature_live_smoke_urns`
(`src/atdd/coach/gate/smoke_obligation.py:160-168`) resolves a feature URN to a plan
file and, when there is none, logs at **debug** and returns `[]` — so a dangling
Feature field **silently waives the issue's SMOKE obligation**. Left alone, E003's
SMOKE acceptance would never be owed at the gate. (That it fails *silently* is the
same defect class this issue exists to fix.)

Resolved by revising the field to the authored home,
`feature:isolate-provider-boundary:surface-undrainable-outbox`, via
`atdd author issue --revise` (never `gh issue edit`). `wagon:isolate-provider-boundary`
is the correct owner on the merits: it owns "core is provider-free" and the provider
registry that a drainability assessment must consult.

**The general defect is already filed as #1635** ("Issues carry no resolvable feature
binding, so nothing can find an issue's WMBTs and the coach reports 'none found' for
every issue", OPEN at `atdd:RED`) — which is also why `atdd coach enter 1655` reports
`WMBTs: none found`. It is **not** re-filed here: minting a second issue for a defect
already in flight is precisely the duplicate-creation failure mode §3a documents.
The evidence this issue contributes to it — the silent-waiver mechanism at
`smoke_obligation.py:160-168`, and the census showing 3 of umbrella #1652's 4 issues
carried dangling feature URNs — belongs on #1635, not in #1655's scope.

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
atdd state outbox discard 22 --reason "version 4.23.0 already tagged+on PyPI since 07-23; born stranded (§3c)"
```

Rows **22–26** were queued after this list was drafted and need their own
dispositions; re-run `atdd state outbox list` before acting, because the set will
have moved again. Rows 24–26 in particular should be re-applied through the revise
path (their targets are live issues) rather than discarded blind.

Row **6** is deliberately left pending: it is the one row whose content is still
live (§3b). It should be re-applied to #1361 through #1654's revise path and
discarded then — leaving a bounded, explained remainder, which is what "bounded with
a reason" means in the issue's own success criteria.

`atdd state outbox check` then reports the bounded remainder instead of the whole
backlog, and says why.

**Not executed here, by instruction.** Three workers were reading this store
concurrently, and running a disposition sweep against it mid-flight is an operator
decision, not a worker's. Building the mechanism is #1655's deliverable; running it
is not.
