# Two-worktree probe: the base-commit anchor (#2041)

A single-checkout test is structurally incapable of reproducing this — one checkout
holds one HEAD, so it cannot construct a foreign base. This probe uses **two
worktrees at different HEADs sharing one Control Root**.

## Corpus facts (this repo, 2026-09-19)

```
worktrees                  : 122
distinct HEADs             : 114
store_metadata             : {'dirty': 'clean'}     -- no base has ever been stamped
resolve_control_root(main) : /Users/alecfokapu/Github/atdd
resolve_control_root(wt-N) : /Users/alecfokapu/Github/atdd   -- one store, though each
                                                                worktree carries its own .atdd
```

## The hypothesis, tested

> `reconcile` may already refuse a base it did not hydrate from, or the stamp may be
> scoped in a way the review missed.

**Partly true — and the true part is a scoping.** `assert_reconcilable` refuses any
Control Root without its own `.git`, and both `hydrate_store` and `reconcile` call it:

```
assert_reconcilable(/Users/alecfokapu/Github/atdd)       -> REFUSED (SharedStoreReconcileRefused)
assert_reconcilable(/Users/alecfokapu/Github/atdd/main)  -> ALLOWED
```

So the defect is **latent in this repo** — and the same guard means **the cutover
cannot hydrate here either**. The anchor defect sits behind a refusal that also
blocks the operation that would expose it.

## Where the refusal does not apply, it reproduces exactly

Layout: a Control Root that is itself a git checkout, with a worktree beneath it.
Both resolve to one store.

```
control root HEAD  = a7cf6e7bb89b        worktree wt-b HEAD = 0aee466474a6

1. assert_reconcilable(control root)      -> ALLOWED
2. first hydrate stamps store_base_commit -> a7cf6e7bb89b   (the root's HEAD)
3. freshness as seen from wt-b            -> base=a7cf6e7b head=0aee4664 stale=True
4. commit_exists(foreign base) from wt-b  -> True
```

Line 4 is the defect. `gitstore.commit_exists` answers *"reachable in this
repository"*; worktrees share one object database, so a base another worktree
hydrated from is always reachable. Its docstring says it exists so "reconcile must
refuse rather than replay onto the wrong public state (P001)" — it returns true for
exactly that case.

And reconcile proceeds:

```
base (stamped by root) = d2f952f53f2c
wt-b HEAD              = 0aee466474a6      foreign base: True

RESULT: reconcile PROCEEDED
  ReconcileResult(mode='hydrate', base_commit='d2f952f5…', head='0aee4664…', hydrated=1)
```

It names the foreign base as its own and reports success.

## Consequences for the design

- `commit_exists` **cannot** be the fix point: in a shared object database the answer
  to its question is always yes. The guard needs provenance, not a stricter call.
- The acceptance must be **two-worktree**. A single-checkout given cannot hold two
  HEADs, which is why the rehearsal reported green while this was true.
- `assert_reconcilable` must not be weakened to make the fix testable — it is the
  only thing standing between this repo and the defect today.

## Relation to #2029

#2029's Done-when has four clauses: the fenced store, `cutover` 3/3, a verified
backup, writer quiescence. None mentions cross-worktree anchoring. All four can pass
while the store's anchor is meaningless to 113 of 114 worktrees. Recommended as a
fifth clause — see #2041 Decision 4.

---

# Part 2 — the reproduction, through the real CLI

Part 1 called `reconcile(root, head=head_wt)` from Python, passing the invoking
worktree's HEAD explicitly. **The CLI never does that.** `_cmd_reconcile` passes
`head=args.head`, which is `None` unless the operator types `--head`, so
`reconcile` falls back to `gitstore.head(control_root)` — the **control root's**
HEAD, not the invoking worktree's. Part 1 therefore demonstrated the guard's
blindness under a call that does not occur in practice. This part uses the
shipped commands only.

## Setup

```
root/            control root, git checkout + .atdd, HEAD = C2 (7fb8b9e5)
root/worktrees/B a worktree of it,                  HEAD = C1 (b0e2a653)
```
One store, one committed projection at C2.

## Transcript

```
$ atdd state hydrate --root root                    # run from the control root
hydrated 1 object(s) from …/.atdd/state/projection
store_base_commit -> 7fb8b9e5e08b                   # the control root's HEAD (C2)

$ cd root/worktrees/B                               # B is at C1
$ atdd state freshness
store is fresh at 7fb8b9e5e08b                      # <- C2. B is at C1.

$ atdd state reconcile
reconciled 7fb8b9e5e08b → 7fb8b9e5e08b (hydrate)    # <- both sides are C2
  hydrated 1 object(s) from the incoming projection
```

## What this proves, and what it refutes

**Refuted, as stated.** "A reconcile in another worktree replays onto a base it
never hydrated from" does not happen in the CLI path — because there is no
per-worktree base to be foreign to. Reconcile never consults the invoking
worktree's HEAD at all.

**Proven, and sharper.** The invoking worktree's HEAD is structurally irrelevant
to every store command it runs. Both operands of the staleness comparison come
from the control root, so `freshness` reports **"fresh"** to a worktree that is a
commit behind — and would report "fresh" to all 114 distinct HEADs. The check
that exists to detect divergence cannot observe the only divergence that matters
here.

**No data loss observed on this path.** B's local overlay object survived the
reconcile (`hydrate` mode, no deletions). The defect is a silent wrong answer,
not destruction — do not overstate it.

**And the guard behind it is still blind.** Part 1 stands as the second finding:
*if* a fix starts passing the invoking worktree's HEAD, `commit_exists` cannot
then reject a foreign base, because worktrees share one object database
(`commit_exists(foreign base) -> True`). A repair that only routes the right HEAD
in would land straight on an unusable guard.

## Consequence for the design

Two defects, in order:

1. Store commands resolve HEAD from the control root, so a worktree's own HEAD
   never reaches the comparison. Fixing only this exposes (2).
2. `commit_exists` cannot express "did *this* checkout hydrate from it", so it
   cannot reject a foreign base once per-worktree HEADs start arriving.

A fix for (1) without (2) converts a silent "fresh" into a silent wrong replay.
