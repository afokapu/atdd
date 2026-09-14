# #1622 lab — re-measuring the five keys the findings left open or stale

Measured 2026-09-13 against a read-only copy of the Control Root store, on a checkout
rebased onto `origin/main`. The 2026-08-01 findings were taken on a store of ~803 work
items; it now holds 1,035, and `origin/main` has moved 206 commits. Counts below are
**projectable** (non-`COMPLETE`), the findings' own scope.

| key | proj | non-null | then | now |
|---|---|---|---|---|
| `branch` | 302 | 185 | STRIP (115 proj, 48 non-null) | **STRIP — rationale replaced** |
| `worktree_path` | 130 | 130 | DROP (25 proj) | **DROP — confirmed, stronger** |
| `feature` | 390 | 348 | GROW (96 proj, 33 non-null) | **STRIP — ruled 2026-09-13** |
| `feature_urn` | 4 | 4 | never dispositioned | **DROP — after recording its evidence** |
| `file` | 7 | 0 | never dispositioned | **DROP — trivial** |

## `branch` — STRIP stands, but not for the reason given

The findings ruled STRIP because "readers (2, neither a decision module)" and
`WorkItemReader.branch()` has "test-only callers". The first half is now false: #1720
landed after the findings and made `data.branch` the **primary index** of
`_resolve_branch_in_store` (`coach/commands/issue.py:134`) — the pre-commit registration
gate. That is a live gate read, not a display read. (`WorkItemReader.branch()` still has
no live callers; that half holds.)

STRIP survives anyway, because of the CI-only ruling. The gate reads the **live SQLite
store**, which is never rebuilt from the projection. Branch bindings are per-machine
state written by `atdd worktree create` on the host that needs them, so a peer hydrating
the projection was never going to inherit a useful value regardless.

Recorded so it is not re-litigated: **the reason is now "its one gate reader reads the
live store", not "nothing important reads it".** If the projection ever becomes a
recovery source, this flips.

## `worktree_path` — DROP, and it cannot be anything else

130 projectable carriers, **all non-null**, every one an absolute host path. It cannot be
grown: `_HOST_PATH_RE` matches `/Users/`, `assert_deterministic` runs over the whole
document before a byte is written, and one leak leaves the entire projection unwritten.
The 5.2× growth since 2026-08-01 strengthens the original call rather than weakening it.

## `feature` — GROW refuted by the writer, not by the counts

`planner/commands/author_issue.py:187`:

    feature = str(spec.get("feature") or "feature:author-atdd-substrate:author-issue-body").strip()

**172 of the 348 non-null values (49%) are exactly that fallback.** Another 8 are the
literal string `TBD` and 9 more are TBD-prose. So about half the corpus does not record a
feature binding; it records that nobody supplied one.

Growing it would publish 172 false bindings as authoritative shared state.

The precedent is already in the contract. The line above does the same for `train`
— `str(spec.get("train") or "train:substrate:author-artifacts")` — and `train` **is**
already a `FIELD_TYPES` field: 53 of its 271 non-null values (19%) are its own default,
and 12 more are bare stems like `0007-enforce-extension-conventions` rather than URNs.
That is what growing a defaulted field produced last time, at 19%. `feature` is at 49%.

Live bag reader: one — `coach/commands/issue_feature_binding.py:280`, feeding the
`issue_feature_binding_scanner` validator. (`WorkItemReader.feature()` has no live
callers; the apparent hits are `URNGrammar.feature`, the name collision the findings
flagged.)

**Ruled 2026-09-13: STRIP**, and the writer defect is split out as **#2006**.

STRIP rather than GROW because growing publishes 172 false bindings as authoritative shared
state, and the `train` precedent shows what that produces. STRIP rather than "fix the writer
first" because the two are independent: the one live bag reader
(`issue_feature_binding_scanner`, via `issue_feature_binding.py:280`) reads the **live**
store, which the projection never rebuilds — the same reasoning that saved `branch`. So
stripping costs that validator nothing, and #1622 does not wait on #2006.

What #2006 owns: stopping the default at `author_issue.py:186-187` for both `feature` and
`train`, and deciding what an unsupplied binding stores instead. It explicitly does **not**
own backfilling the 172 + 53 affected work items — that needs its answer first.

Note `train` is not covered by this ruling. It is already a `FIELD_TYPES` field carrying 19%
defaulted values today; #1622 changes nothing about it, and #2006 only stops the inflow.

## `feature_urn` — DROP, but record this first

Only 4 projectable carriers, and no bag reader anywhere in `src`. It would be trivial
except that it **contradicts** `feature` on 3 of its 5 objects — and on two of those,
`feature` holds the hardcoded default while `feature_urn` holds a real binding:

| object | `feature_urn` | `feature` |
|---|---|---|
| (author-atdd-substrate item) | `…:substrate-spine` | the default |
| `projection-contract-diverged-from-…` (#1622 itself) | `…:migrate-store-projection` | `None` |
| `provider-executes-declared-trains-…` | `…:enforcing-phase-transition-gate` | the default |
| `reduce-silent-swallow-…` | `…:enforce-conventions-ci` | same ✓ |
| `unverified:issue-1524` | `…:place-worktrees` | `None` |

Four rows of corroborating evidence that `feature` is unreliable — including #1622's own
work item. Drop the key; keep this table.

## `file` — DROP

7 carriers, **0 non-null**. Pure null-seeding from `coach/commands/branch.py:333` and
`coach/commands/issue.py:2289`, both literally `"file": None`. No work-item bag reader.
Drop it, and stop the two seeders so it does not return.

## Running total

These five settle 833 of the 3,708 unprojectable-field defects. With `issue_number` and
`_recovery` (1,027, settled by the CI-only ruling), **1,860 of 3,708 — just over half.**
