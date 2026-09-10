# Spike — what would write-time train validation reject? (#1890)

**Question.** `atdd update <N> --train <value>` writes whatever it is given. The
transition gate then refuses the issue at PLANNED because the value resolves
against nothing. Which validation rule belongs on the write path — and what does
each candidate cost on real data?

**Why a spike.** The defect needed no reproducing: `atdd update 1888 --train
INVALID` was accepted outright, observed. What was unknown is the *blast radius*.
"Reject legacy, we have a canonical format" is the obvious rule and it is a
premise about migration state, not about code — not inferable by reading either
side of the comparison.

**Method.** Two attempts. The first is recorded because its failure is a result.

1. *(abandoned)* A throwaway project plus the real CLI. Could not run: `atdd
   update` resolves a live GitHub issue through `gh` and a Control Root, so the
   write path cannot be exercised against a synthetic project at all. When a tool
   is coupled to external state, do not fake the world — lab the function and
   measure the data.
2. *(used)* Score each candidate rule against every `--train` value the repo's own
   source passes, and against the real train registry.
   Harness: `labs/1890-train-write-validation/blast_radius.py`.

## Measured

Registry holds **21** train identities: **14 canonical** (`train:<subject>:<slug>`)
and **7 legacy** (`NNNN-slug`).

| candidate rule | rejects (distinct / call sites) | verdict |
|---|---|---|
| A — reject unregistered | 2 / 6 real | **correct target** |
| B — reject legacy FORMAT | 1 / 4 | premature: also orphans 7 REGISTERED legacy trains |
| C — A or B | 2 / 6 | same as B's problem |

Resolution of the values actually in use:

    DANGLING   0003-author-substrate       ← passed by the repo's own CLI smoke tests, 2 sites
    RESOLVES   0007-enforce-extension-conventions
    RESOLVES   train:object-conflict-resolution:project-state   (dispositions.TRAIN_ID, a shipped default)
    DANGLING   train:commons:spine         ← in-memory merge fixtures only, never written by the CLI
    DANGLING   INVALID                     ← accepted by `atdd update 1888 --train INVALID`

## Findings

1. **The write path validates nothing, and it has already produced bad data.**
   `0003-author-substrate` resolves against no registry entry and no loose
   `plan/_trains/*.yaml` stem, and the repo's own smoke tests write it.
2. **Rejecting the legacy FORMAT today is wrong**, and this is the finding that
   changed the fix. `train.schema.json:20` states the legacy form "is still
   accepted DURING the migration transition (schema-first, data-follows) and is
   retired once worker C4 relocates every train." 7 of 21 trains are still legacy
   and registered. A format rule would orphan trains that are correctly declared.
   The canonical direction is right; the migration is simply not finished.
3. **The rule that bites is registration, not shape.** It rejects `INVALID` and
   `0003-author-substrate` — the actual bad data — and rejects nothing that
   resolves.
4. `train:commons:spine` is a false alarm: merge-matrix fixtures construct it
   in-memory and no CLI writes it. Worth recording because a rule keyed on
   "appears in source" would have flagged it.

## Consequence for the fix

Validate at write time with the SAME resolver the read path already uses
(`normalize_train_id` + the registry/loose-stem union), so the two paths cannot
disagree — which is the #1850 defect one layer up. Accept a registered legacy id
but name its canonical successor in a deprecation notice, so the migration is
pushed forward without stranding declared trains. Promote to a hard format
refusal when the registry holds zero legacy entries; that condition is
mechanically checkable, so it does not need a human to remember.

## Disposition

Harness kept under `labs/`. The `proj/` world it builds is disposable.
