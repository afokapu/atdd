# #1999 — DISCOVERY: can the merge gate hold the operator's signature?

The `INIT -> PLANNED` work for #1999. **Discovery only — no fix proposed here, no
runtime code changed.** Date: 2026-09-13. Control Root: `/Users/alecfokapu/Github/atdd`.

The issue filed one OPEN RISK and told this phase to settle it first:

> `auto-phase` shells `atdd coach transition <N> COMPLETE` after the merge. Gating that
> edge means the operator's token must already exist when it runs, and the token observed
> on 2026-09-13 was bound to the branch with a 24h expiry — while the merge may delete the
> branch. Whether a branch-bound token survives its branch decides whether this design
> works as written or needs the token bound to the issue instead.

It is settled: **the branch binding is not the risk.** A larger one sits behind it, and a
third finding invalidates Decision 6c as written. All three are measured below.

---

## Instrument check (done first)

Every claim the issue body asserts was re-measured against the shipped code before
anything new was concluded, so a new finding cannot be an artefact of a broken probe.

```
gate.transitions = {'PLANNED->RED': True, 'SMOKE->REFACTOR': True}

edge                     autonomy(from) gated?  required_for  ApprovalTokenGateCheck
PLANNED->RED             operator       True    True          FAIL
RED->GREEN               agent          False   False         NOT_APPLICABLE
GREEN->SMOKE             agent          False   False         NOT_APPLICABLE
SMOKE->REFACTOR          agent          True    True          NOT_APPLICABLE
REFACTOR->COMPLETE       operator       False   False         FAIL
INIT->PLANNED            operator       False   False         FAIL
INIT->RESOLVED           operator       False   False         FAIL
INIT->OBSOLETE           operator       False   False         FAIL
SMOKE->OBSOLETE          agent          False   False         NOT_APPLICABLE
```

Reproduces the issue's table exactly: the machine already wants a signature at the plan
and at the merge, already waives the middle one, and `approval_required_for` disagrees
with the check on `SMOKE->REFACTOR` (says True, check waives) and on
`REFACTOR->COMPLETE` (says False, check fails). The instrument is sound.

The last two rows are new, and the last one is finding D3.

---

## D1 — The branch binding survives the merge. The open risk as filed is closed.

`approval_binding.resolve_issue_branch` reads the branch from the **State Store** —
`external_refs(github/issue/N) -> objects.data["branch"]` — and its module header says
why it deliberately does not run `git rev-parse`:

> THE BRANCH COMES FROM THE STORE, NOT FROM THE CWD (#1721 Decision).

So the binding names a *record*, not a ref. Deleting `origin/<branch>` on merge cannot
invalidate it, because nothing in the verification path asks git anything. `atdd cleanup`
deletes git refs (`git branch -D`, `cleanup.py:214-216`) and writes nothing to the store.
What the binding actually catches — its header again — is **drift over time**: a rename, a
recreated worktree, a re-pointed work item. A merge is none of those.

The 24h `APPROVAL_TTL` (`approval_binding.APPROVAL_TTL`) is likewise not tight: the token
is minted at REFACTOR and consumed by auto-phase within minutes of the merge, against a
measured widest-observed need of 84 seconds.

**Conclusion: the token does not need re-binding to the issue.** The design works as
written on this axis, and the Notes section's proposed alternative is not needed.

## D2 — But the token is invisible where the transition actually runs. (blocking)

The risk is not *when* the transition runs, it is **where**.

| Fact | Evidence |
|---|---|
| the token is a file under the Control Root | `approval_relpath` → `.atdd/runtime/issue-<N>/approvals/<FROM>-<TO>.json` |
| that path is gitignored | `.gitignore:42` — `.atdd/runtime/` |
| `approve` writes nothing else | `approve_command.py:349` is the only write; no store event, no GitHub projection |
| the COMPLETE transition runs in GitHub Actions | `.github/workflows/atdd-auto-phase.yml` — `actions/checkout@v4` + `atdd auto-phase` |
| that runner has no store either | `auto_phase.read_store_phase` is written to degrade to the label; the projection that would carry the store into a checkout (`.atdd/state/projection/`) is **not committed in this repo** — `git ls-files .atdd/state/projection` returns 0 |

So adding `REFACTOR->COMPLETE: true` to `gate.transitions` and changing nothing else makes
**every** post-merge auto-phase run fail: the token cannot exist in a fresh checkout, the
check is fail-closed by design, the issue never reaches COMPLETE and the label never swaps.
The merge lands the code and the lifecycle stops — strictly worse than today, where the
merge lands the code and the lifecycle advances unsigned.

Moving the enforcement to the merge itself does not escape it. `atdd validate coach`'s
`test_pr_merge_blocks_pre_smoke_close` runs in CI and reads the **GitHub label**, and
`atdd-merge-authority.yml` states in its own header that the run "reads NO GitHub API and
no developer SQLite store". Neither surface can see a file under `.atdd/runtime/`.

This is the storage-class defect Decision 3 already names for reviews — `.atdd/runtime/`
is gitignored and per-checkout — arriving at the gate itself. Decision 3 answers it for
the review and leaves it unanswered for the token.

**Four candidate resolutions, for the operator to pick at the `PLANNED->RED` gate.** They
are not equivalent and Phase 1 cannot start until one is chosen:

| # | Shape | Cost | Objection |
|---|---|---|---|
| A | Project the approval into the committed store projection, and have the gate read the projection when no local token exists | the projection is not committed here yet — a real dependency, possibly its own issue | largest change; the cleanest fit with "the record is the store" |
| B | Project the signed token onto the PR (a comment or a check run) and re-verify its signature in CI | small; the threat model already says the token is not a secret (`resolve_signing_key` falls back to a public constant) | Decision 3 calls a GitHub comment "a projection, not a record" — acceptable here *because* the record would still be the store, but it must be argued, not assumed |
| C | Gate the edge only where a human is (local `atdd coach transition`), and have CI's auto-phase skip the gate it structurally cannot satisfy | smallest | a gate with a documented bypass is the thing this issue exists to remove |
| D | Do not auto-advance `REFACTOR->COMPLETE` at all — make COMPLETE an operator-run local transition, and let auto-phase stop at REFACTOR | small, and arguably what "the merge is the irreversible decision" implies | changes the hands-free property #355 built auto-phase for |

Discovery's recommendation was **B** on the reasoning that A's dependency was open-ended.

**OPERATOR DECISION, 2026-09-13: A.** The premise of that recommendation is wrong. A's
blocker is #1622 — *"atdd state project refuses every object: the projection contract has
diverged from the store object shape"* — which is at **SMOKE** with a live worktree and is
about to land. `git ls-files .atdd/state/projection` returns 0 *because* `atdd state
project` refuses on the first object, not because the mechanism is missing; #1622's
Done-when is exactly "writes one document per projectable work item instead of refusing".

So A is not the large change Discovery costed. It is the option whose dependency is nearly
merged, and it is the only one of the four where the token the gate reads and the record
the store keeps are the same artifact — no second carrier to keep correct, nothing to
re-verify, and no bypass. B's PR projection would have been a second delivery path for the
same fact, which is the objection Decision 5 already raises against a new channel.

**Consequence for sequencing: #1999 depends on #1622.** Phase 1's config change is gated on
the committed projection existing. Everything else in Phase 1 — the hint fix, the
`transition_leash` and `escape_invariant` corrections, the D3 waiver fix — is independent
of it and can proceed.

## D3 — Decision 6c is inert from three of OBSOLETE's seven sources.

The escape invariant is stated by **destination** ("no transition INTO ..."), and
Decision 6c asks the config to be keyed the same way. But `ApprovalTokenGateCheck`'s
waiver is keyed by **source**: `_autonomy_waiver` calls `_declared_autonomy(ctx.from_phase)`
and returns `NOT_APPLICABLE` on an exact `agent`.

Measured autonomy per phase: `INIT/PLANNED/REFACTOR/BLOCKED = operator`;
**`RED/GREEN/SMOKE = agent`**.

So `RED->OBSOLETE`, `GREEN->OBSOLETE` and `SMOKE->OBSOLETE` are waived before the token is
ever looked for — confirmed in the table above, where `SMOKE->OBSOLETE` returns
`NOT_APPLICABLE`. A `*->OBSOLETE` config key would therefore gate four of the seven edges
and silently waive three, which is the same shape of failure 6c was written to prevent.

The fix is one sentence of policy, not a bigger change: **an escape destination is never
waived by source autonomy.** `_autonomy_waiver` must consult `ESCAPES` (already exported by
`phase_edges`) and decline to waive when `ctx.to_phase` is one. That belongs in Phase 1
beside the `transition_leash` correction, and it needs its own gate test, because nothing
today asserts the waiver's keying.

---

## What Discovery did not settle

- **What the plan is reviewed against at gate 1.** Left open by the issue by design
  (#1984 is where recording Discovery lands); this document is itself the artefact that
  question is about, which is worth noting and not worth resolving here.
- **Whether the OBSOLETE destination key needs a `gate.transitions` schema change**, or
  whether `is_transition_gated` can grow destination matching compatibly. A Phase 1
  question, cheap once D2 is decided.

## Consequences for the plan

1. The Notes OPEN RISK is closed by D1 and **replaced** by D2, which is blocking and needs
   an operator decision before Phase 1 starts.
2. Phase 1 gains the `_autonomy_waiver` escape-destination correction (D3) and a test for it.
3. `REFACTOR->COMPLETE: true` in `.atdd/config.yaml` is no longer a one-line change: it is
   the *last* step of option A, landing after #1622 makes the committed projection real.
4. **#1999 depends on #1622**, and that dependency is on the config line alone — the rest of
   Phase 1 does not wait for it.
