# Dispatch 2 — #1635 decomposition manifest

**Result:** `sub_issues_summary` moved `{total: 0}` → `{"completed":1,"percent_completed":11,"total":9}`.
Six children minted, eight linked, one edge (#1689) found already present.

---

## STEP 0 — measurements

### Legacy-train blast radius

Read-only against the live store (`/Users/alecfokapu/Github/atdd/.atdd/state/state.sqlite`),
846 `work_item` objects, classified with the exact regexes from
`src/atdd/planner/commands/author.py`. "Live" = state not in
{COMPLETE, OBSOLETE, ARCHIVED, CLOSED}.

| train form | all | live | share of live |
|---|---|---|---|
| typed `train:<subject>:<slug>` | 136 | 113 | 69.8% |
| legacy `NNNN-slug` | 105 | 34 | 21.0% |
| malformed (neither) | 83 | 15 | 9.3% |
| absent (`data.train` unset) | 522 | 414 | — |

**Typed : legacy = 1.30 : 1 overall, 3.32 : 1 among live items.**

Two things the four-data-point sample could not have shown:

**1. A third state exists.** 83 items carry a `data.train` that is *neither* form — 15 live.
The values are `TBD` (56), `none` (14), `N/A` (5), `T001` (2), `substrate`, `t0006`,
`TBD <!-- will be defined in #110 / P001 -->`, `N/A (toolkit infra)`,
`N/A (toolkit lacks plan/ until #103 ships)`, and
``0001-self-compliance-validate` (proposed)``. The legacy-vs-typed framing has no bucket for
these, and a grammar that only learns to say `DEPRECATED` for `NNNN-slug` will still report
these as fine.

**2. Almost all legacy usage is already migratable.** `plan/_trains/_aliases.yaml` (#1421)
maps legacy → typed for `0001`–`0006`, `0206-reconcile-dirty-store` and
`0306-resolve-object-conflict`. Splitting the 105 by alias coverage:

| | all | live |
|---|---|---|
| legacy **with** an alias (auto-resolvable) | 95 | 26 |
| legacy **without** an alias (genuinely orphaned) | **10** | **8** |

All 10 orphaned items sit on a single train: `0007-enforce-extension-conventions`.

**Consequence for Child A (C6/#1686 + C7/#1698):** the retirement blast radius is not 105,
it is **8 live work items on one train**. The wording was scoped accordingly — #1686 keeps
the unblocked reporting half and now carries this table; #1698 states the true, small radius
and names the rename ownership (not the volume) as what blocks it.

**Extra hazard found:** the legacy number space is reused. `0206` names
`reconcile-dirty-store` in the alias map and `decommission-orphan-detector` in
`plan/_trains/`. Two different trains, one number.

### Re-verification against the current tree (`da2e8cc3`)

| claim | operator's figure | current | verdict |
|---|---|---|---|
| `_TRAIN_ID_RE` line | 331 | **329** | drifted 2 lines |
| `_TYPED_TRAIN_ID_RE` line | 335 | **333** | drifted 2 lines |
| `govern-providers` has no typed train | asserted | **confirmed** | appears only in `0007`, `0205`, `0206` — all legacy-form — plus `_interlockings/enforce-extension-conventions.yaml`. It is a *wagon*; no typed train covers it. |

---

## Finding: the backfill already ran, and the C4 numbers moved

The brief's `would_write=177, unresolved=531` no longer reproduces. Current measurement
(`backfill_feature_bindings(dry_run=True)`):

```
would_write (body-derivable):  0
unresolved (NOT body-derivable): 529
```

I ruled out an invocation artifact before accepting it: the resolver is healthy
(`feature:govern-lifecycle:bind-issue-feature` → 3 WMBTs,
`feature:govern-lifecycle:reliable-manifest-registration` → 1), and of the 529 remaining,
367 carry no body `Feature` row at all while 162 carry one that names a wagon or feature
absent from `plan/` (e.g. `feature:mediate-worker-decisions:bridge-cmux-feed`, `TBD`,
`polyglot-config-awareness`).

The cause is in the store's own event log: **180 `issue_revised` events carrying
`fields: ["feature"]`, all landing at `2026-08-03 02:06:31`–`02:06:32`.** The backfill was
executed for real against the live store between dispatch 1 and this dispatch, in one batch.
`#1689` — which owns exactly that work — was authored minutes later (`02:08:15`) and linked
to #1635 before I began.

Two consequences, both folded into the minted bodies:

- **C3 (#1695) is sharper, not weaker.** A repair tool with no CLI surface has already
  mutated 180 live work items through a non-CLI entry point. Unreachable *and* already used.
- **C4 (#1696) is 529, not 531**, and its body-derivable half is now **0 remaining** — there
  is nothing left for a machine to derive. Every remaining binding must be authored by a
  person, which is what makes it a planning backlog rather than a code fix.

Every one of those 180 writes emitted `fields: ["feature"]` and **no body write** — which is
C2 (#1694) measured at scale rather than argued.

---

## The children

| C | # | Title (abbrev.) | Slug | Minted / linked | Edge verified |
|---|---|---|---|---|---|
| C1 | 1676 | `atdd update --feature-urn` is a silent no-op | *(pre-existing)* | **linked** (closed) | ✅ in `sub_issues` |
| C2 | 1694 | `--revise --feature` writes only the store, leaving the body Feature row stale | `revise-feature-leaves-body-row-stale` | **minted** | ✅ |
| C3 | 1695 | `backfill_feature_bindings` has no CLI surface | `backfill-feature-bindings-has-no-cli-surface` | **minted** | ✅ |
| C4 | 1696 | 529 work items need authored bindings, not a backfill | `author-feature-bindings-for-underivable-work-items` | **minted** | ✅ |
| C5 | 1697 | `live_smoke_obligation` passes SMOKE→REFACTOR on an empty obligation | `smoke-gate-green-on-empty-obligation` | **minted** | ✅ |
| C6 | 1686 | Legacy `NNNN-slug` train reported VALID | *(pre-existing)* | **linked + scoped** via [comment](https://github.com/afokapu/atdd/issues/1686#issuecomment-5161625483) | ✅ |
| C7 | 1698 | Retire the legacy train form — **BLOCKED** | `retire-legacy-train-id-form` | **minted** | ✅ |
| C8 | 1699 | #1635's own body↔store binding disagreement | `reconcile-1635-body-store-feature-binding` | **minted** | ✅ |
| — | 1689 | 282 issues declare a feature that never reached the store | *(pre-existing)* | **already linked before this dispatch** | ✅ |

All six minted children were created with `atdd author issue` (never `gh issue create`),
each given a **typed** train and a feature URN that resolves against `plan/`, then revised
with a real body via `atdd author issue --revise <N> --body-file`. All sit at `INIT`; none
was transitioned.

### Binding parity on the new children

The program's own thesis, applied to its own output. Every minted child, store vs. body:

| # | store `data.feature` | body `Feature` row | match | train form |
|---|---|---|---|---|
| 1694 | `feature:govern-lifecycle:bind-issue-feature` | same | ✅ | typed |
| 1695 | `feature:govern-lifecycle:bind-issue-feature` | same | ✅ | typed |
| 1696 | `feature:govern-lifecycle:bind-issue-feature` | same | ✅ | typed |
| 1697 | `feature:govern-lifecycle:smoke-false-green-prevention` | same | ✅ | typed |
| 1698 | `feature:author-atdd-substrate:author-issue-body` | same | ✅ | typed |
| 1699 | `feature:govern-lifecycle:bind-issue-feature` | same | ✅ | typed |

Parity was re-checked *after* the body revise, and held. Notably `--revise --body-file`
writes GitHub and the store identically (verified byte-for-byte on all six). **The
divergence C2 names is specific to `--feature`, not to `--revise` generally** — a useful
narrowing for whoever fixes #1694.

---

## Verification of the linkage

```
$ gh api repos/afokapu/atdd/issues/1635 --jq .sub_issues_summary
{"completed":1,"percent_completed":11,"total":9}
```

```
$ gh api repos/afokapu/atdd/issues/1635/sub_issues --jq '.[] | "\(.number) [\(.state)]"'
1689  [open]
1676  [closed]
1686  [open]
1694  [open]
1695  [open]
1696  [open]
1697  [open]
1698  [open]
1699  [open]
```

**`total` is 9, not the 8 the brief predicted.** The ninth is #1689, which was already a
sub-issue of #1635 when I started — so the brief's `{total: 0}` reading was stale by the time
I ran, for the same reason the 177 was: another session minted and linked #1689 at
`02:08:15`. I did not create it and did not remove it; it belongs in this decomposition
(it owns the body-derivable half of C4). `completed: 1` is #1676, which is closed.

---

## Not minted, because something already owns it

- **The body-derivable half of C4** → **#1689**. C4 (#1696) was scoped to the
  *non*-derivable 529 and explicitly out-of-scopes #1689's set, rather than duplicating it.
- **Route-space binding on issues** → **#1565**. Checked before minting C4 and C8, as
  instructed. It binds `interlocking_id` / `route_id` / `residual_kind` — a *different field*
  on the same bodies, and it explicitly out-of-scopes backfilling the 708 existing bodies.
  It does not own the feature-binding seam, so C4 and C8 are not duplicates. #1696 names it
  as adjacent-not-overlapping so the two backfills do not collide later.
- **The planner-side live-smoke obligation** → **#1609**. Confirmed complementary: its body
  explicitly out-of-scopes `atdd.coach.gate.smoke_obligation`. C5 (#1697) cross-references it
  and owns only the gate.

---

## Commands that reported success while writing nothing

None in this dispatch. One command **failed loudly and correctly**, and is recorded because
the first attempt looked like a linkage bug:

```
$ gh api repos/afokapu/atdd/issues/1635/sub_issues -f sub_issue_id=5045650403
422: Invalid property /sub_issue_id: `"5045650403"` is not of type `integer`
```

`-f` sends the value as a string; the endpoint requires an integer. Re-running the same
allowlisted URL with `-F` (typed field) linked all eight. This was my own flag error, not a
permission or an API defect — worth noting only because eight consecutive "Invalid request"
lines read like a blocked route at first glance.

Also verified rather than trusted: all six `atdd author issue --revise ... --body-file` calls
exited 0 **and** were confirmed to have replaced the stub on both GitHub and the store.

---

## Surfaced for the operator (I am not permitted to run these)

- Nothing needs transitioning for this dispatch to be complete — all nine children sit where
  they should. Flagging only that **#1698 (C7) must not be started**: it is blocked on an
  operator decision about who owns the `plan/` URN rename — #1698 itself, or the
  `refactor/recompose-wagons-from-wmbts` branch, which proposes renaming the same identity
  space. The body says so.
- **#1699 (C8) is first in sequence.** #1635 currently sits at `SMOKE` while failing its own
  C011 binding scanner.
- Unrelated to this dispatch, still true: `atdd state doctor` reports INVALID with
  per-worktree operational installs across the sibling worktrees. I did not run
  `atdd state migrate-layout`.
