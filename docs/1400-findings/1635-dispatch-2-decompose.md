# Dispatch 2 — DECOMPOSE #1635 and mint its children

Your Dispatch 1 verdict was excellent and is fully accepted. This dispatch acts on it.

**#1635 currently has `sub_issues_summary = {total: 0}`.** A program about issues failing to
resolve their WMBTs has zero sub-issues. That ends here.

---

## STEP 0 — measure first, mint second

One measurement gates the wording of a child below. Do it before anything else:

**Legacy-train blast radius.** How many live work items carry a legacy `NNNN-slug`
`data.train` versus a typed `train:<subject>:<slug>` one? Read-only against the live store.
Report both counts and the ratio. Child A's wording depends on it — I have only four data
points (#1674, #1676 legacy; #1635, #1622 typed) and that is not a distribution.

Also re-verify, against the CURRENT tree (the branch has since merged `origin/main` at
`da2e8cc3`, picking up `563ef447`):
- `_TRAIN_ID_RE` and `_TYPED_TRAIN_ID_RE` line numbers in `src/atdd/planner/commands/author.py`
  (operator cited 331 and 335; #1677 churn makes these unreliable)
- that `govern-providers` genuinely has **no typed train**, appearing only in `0007`/`0205`/`0206`

---

## The decomposition — 8 children. TWO ALREADY EXIST.

**Do not re-mint #1676 or #1686.** They are filed. Link them.

| # | Child | Status |
|---|---|---|
| C1 | `atdd update --feature-urn` writes the dead key `data.feature_urn`; every reader reads `data.feature`. Repoint or fail-close. | **= #1676, EXISTS — link only** |
| C2 | `--revise --feature` is store-only: it leaves the body's Feature row stale, creating the body↔store divergence #1676's own done-when forbids. Close the body half. | MINT |
| C3 | `backfill_feature_bindings` has no CLI surface — definition + one test, no `cli.py` wiring. The repair tool this program built is unreachable by an operator. | MINT |
| C4 | 531 work items carry no `data.feature` and are **not** derivable from a body (measured `would_write=177, unresolved=531`). They need authored bindings — a planning backlog, not a code fix. | MINT |
| C5 | `live_smoke_obligation` passes SMOKE→REFACTOR as "not applicable" whenever `acceptance_urns` is empty — including when feature AND train both resolve (measured on #1635 itself). A green certifying nothing. | MINT |
| C6 | Legacy `NNNN-slug` train id is reported **VALID**. Fail loud: report `DEPRECATED`/`LEGACY` at every surface that prints it. No migration, no blast radius. | **= #1686, EXISTS — link + scope it to this half via `gh issue comment`** |
| C7 | Retire the legacy train form entirely. **BLOCKED** — needs `0007`/`0205`/`0206` renamed and a typed train minted for `govern-providers`, which has none. | MINT, and say BLOCKED in the body |
| C8 | #1635's own body↔store binding disagreement: body says `feature:govern-lifecycle:bind-issue-feature`, store says `feature:govern-lifecycle:reliable-manifest-registration`. Its own C011 scanner flags it. | MINT |

### Sequencing to record in the bodies

- **C1 → C2** — C2 closes the half C1's fix would otherwise leave open. Same file family.
- **C8 first** — the program cannot credibly ship a binding validator while failing it.
- **C5 after the binding work.** #1609 is **complementary, not overlapping**: its body explicitly
  out-of-scopes `atdd.coach.gate.smoke_obligation`. It owns the plan-side obligation; C5 owns the
  gate. An issue with `data.feature=NULL` reaches no feature, so no #1609 rule can ever fire for
  it. **Cross-reference #1609 in C5's body; do not duplicate it.**
- **C7 is blocked on an operator decision** about who owns the `plan/` URN rename — C7 or the
  `refactor/recompose-wagons-from-wmbts` branch, which proposes renaming the same identity space.
  Say so in the body. Do not start C7.
- **Check #1565** ("bind issues to route-space", child of umbrella #1576) before minting C4 or C8
  — it is the nearest neighbour to issue-side binding. If it already owns a seam, link it instead
  of minting a duplicate.

---

## How to mint and link

```
atdd author issue --title "<title>" --slug "<slug>"
```

`gh issue create` is PROHIBITED. `atdd author issue` has **no `--parent`** on 4.33.0, so parent
in a second step:

```
gh api repos/afokapu/atdd/issues/1635/sub_issues -f sub_issue_id=<ID>
```

⚠️ That endpoint wants the **numeric issue id**, not the issue *number*. Resolve it:

```
gh api repos/afokapu/atdd/issues/<N> --jq .id
```

Your allowlist has exactly two `gh api` patterns — `.../issues/*/sub_issues*` and
`.../issues/* --jq*` — which cover both calls above and nothing else. **If you need a call
outside them, stop and give me the exact command. Do not ask for a wildcard and do not improvise
an alternative route.**

### VERIFY THE LINKAGE — this is the whole point of the program

After linking, confirm:

```
gh api repos/afokapu/atdd/issues/1635 --jq .sub_issues_summary
```

It reads `{"completed":0,"percent_completed":0,"total":0}` right now. It must read `total: 8`
(6 minted + #1676 + #1686). **A program about empty sub-issue edges must not create more empty
ones.** If a link reports success but `total` does not move, that is a finding — report it, do
not retry blindly.

---

## Deliverable

`docs/1400-findings/1635-dispatch-2-manifest.md`, committed on this branch:

- the blast-radius measurement from STEP 0
- a table of every child: number, title, slug, minted-or-linked, and its `sub_issues_summary`
  verification
- the final `sub_issues_summary` output, pasted
- anything you chose NOT to mint because #1565 or another issue already owned it, with the
  issue number
- any command that reported success while writing nothing

Print the path and stop.

---

## Hard constraints

- **No `atdd coach transition`, no `atdd coach approve`.** Denied in your settings, deliberately.
  Surface them to me; the operator runs them. This includes any temptation to advance the new
  children out of INIT.
- **No `gh issue create`, no `gh pr create`.**
- No `--no-verify`, no force-push.
- Do not weaken, skip, or `xfail` any test.
- Do not run `atdd state migrate-layout`.
- Do not implement C1–C8 in this dispatch. **Mint and link only.** The one exception is nothing —
  if you find yourself editing `src/`, stop and ask.
- The dirty `.atdd/baselines/validation/*.yaml` are pre-existing. Leave them.
- If a command reports success, verify it wrote something before believing it.
- If a permission blocks you, **stop and report**. Do not route around it.
