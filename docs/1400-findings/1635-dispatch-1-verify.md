# Dispatch 1 — VERIFY ONLY. Mint nothing, transition nothing.

You are the investigator for ATDD program **#1635** (issue↔feature binding → WMBT discovery).
You are in its worktree on `feat/issue-feature-binding-resolves-wmbts`: 4 commits, OPEN
**draft** PR #1648.

Your entire job this dispatch is to **answer one question with evidence**. Do not implement,
do not mint issues, do not run `atdd coach transition` or `atdd coach approve`.

---

## STEP 0 — do this first, before reading anything else

`docs/1400-findings/` is **untracked in main** and is one `git clean` from gone. Program #1400
nearly lost its planning artifacts exactly this way. Both files are now copied into this
worktree. Commit them here, on this branch, right now:

```
git add docs/1400-findings/
git commit -m "docs: preserve the #1635 investigation brief and prior-session handoff (#1635)"
```

Wait out the pre-commit hook (1–2 min). **Never `--no-verify`.** If the hook rejects the
commit, stop and report why — do not fight it.

---

## Context you must not rediscover

Read `/Users/alecfokapu/Github/atdd/main/ORCH_BRIEF_1635.md` — mechanism, root cause, and an
"Operational law" section. Read `docs/1400-findings/1635-prior-session-handoff.md` for
**environment facts only**: its author states plainly that they know nothing about #1635
beyond the four commit subjects, so it does **not** answer the question below. What it is
good for: the CLI version skew, `atdd state doctor` reporting INVALID for layout reasons
(do **not** run `atdd state migrate-layout`), and the note that
`.atdd/runtime/issue-1635/approvals/PLANNED-RED.json` exists.

Two facts I have already measured from `main`. Do not re-derive them — but **do** falsify
them if you find otherwise:

1. `atdd update --feature-urn` routes `cli.py:803` → `cli.py:2308` → **`IssueManager.update(...)`**,
   the orphaned manager #1477 decommissioned for minting.
2. `git log origin/main..HEAD -- src/atdd/cli.py` on this branch is **EMPTY**. #1635 never
   touched the command #1676 names.

Meanwhile `38bd9f33` *did* ship a feature writer — on a different path:
`revise_work_item_issue(feature=)` in `src/atdd/state/work_item_writer.py`, forwarded by
`revise_issue` / `_publish_revision` in `src/atdd/planner/commands/author*.py`, plus a
`backfill_feature_bindings`.

**`atdd` self-upgraded to 4.33.0 today (#1677).** Re-verify every file:line above against the
installed tree before relying on it, and cite what you actually see.

---

## THE QUESTION

**Does #1635's GREEN commit `38bd9f33` already fix #1676?**

My provisional answer — confirm or refute it empirically:

> **Partially.** It kills #1676's *structural* claim ("the typed `feature` field is unsettable
> after creation by any route") by shipping a writer on the `--revise` path. It does **not**
> touch #1676's *literal* defect: `atdd update --feature-urn` still reports success and writes
> nothing.
>
> If that holds, #1676 is **not** "build a writer" — it is "repoint or fail-close the dead
> second route." A far smaller change, and it must not duplicate `38bd9f33`.

### Answer it by measuring, not by reading

Use a **scratch** work item. Do **not** mutate #1635, #1676, or any live issue, and mint
nothing — use a temp store or an existing throwaway. For each route, record **all three**
surfaces, because the operational law here is that commands report success while writing nothing:

| Surface | How |
|---|---|
| exit code | `echo $?` immediately after |
| store | the typed `data.feature` column, read back independently |
| body | the Feature row in the rendered issue body |

- **Route A:** `atdd update <N> --feature-urn feature:<w>:<n>`
- **Route B:** `atdd author issue --revise <N> --feature feature:<w>:<n>`

For each: does the store column change? do body and store agree? does failure exit non-zero?
#1676 claims Route A writes a **wrong** urn to the body — check that specifically, it is the
sharpest signal.

Then state: **which of #1676's claims survive `38bd9f33`, and which are dead?**

---

## Also in scope (read-only)

1. **Is the WMBT read side actually finished?** `38bd9f33` claims `resolve_wmbts_for_issue`
   walks issue → feature URN → feature YAML `wmbts:` off disk, and that `_fetch_sub_issues`
   and the `atdd-wmbt` label search are gone. Run `atdd coach issues 1635` from this worktree
   and report what the WMBT section prints. The program exists because that section said
   "none found" for every issue. Does it still?
   **First establish which build you are exercising** — the pipx 4.33.0 CLI or this worktree's
   tree. If it is the former, your output says nothing about this branch.

2. **Overlap check before any seam is declared.** One-line summary each for #1676, #1609,
   #1550, #1576, #1553: does it overlap a seam #1635 would cut, and is it already-shipped,
   in-flight, or untouched? Also check the adjacent worktrees
   `refactor/recompose-wagons-from-wmbts` and `refactor/reconcile-wmbt-schema-with-validation-reality`
   — what do they already do to WMBTs?

3. **The `live_smoke_obligation` vacuous pass.** The brief says a work item whose `feature` was
   unset at creation resolves to `acceptance_urns owed: ()`, so SMOKE→REFACTOR passes as "not
   applicable" — a green certifying nothing. Confirm the code path. Does `38bd9f33` change it?
   Does #1609 already own it?

4. **#1635's own lifecycle lag.** Label says `atdd:RED`; a `feat(green):` commit is on the
   branch; the PLANNED→RED approval token exists on disk. Report the phase in **all three**
   places — CLI display, store `objects.state`, GitHub label — and say what the correct next
   transition is. **Do not run it.** I surface it to the operator.

---

## Deliverable

Write `docs/1400-findings/1635-dispatch-1-verdict.md` **in this worktree** (not in main), and
commit it on this branch when done.

Lead with a direct **yes / no / partially** answer to THE QUESTION and the evidence. Then the
four items. Mark every claim **measured** (command + output) or **inferred**. Inferred claims
are fine; mislabelled ones are not.

Print the path and stop. Do not start implementing.

---

## Hard constraints

Your `.claude/settings.local.json` denies some of these outright. The denials are deliberate —
**do not route around them, surface them to me instead.**

- No `atdd coach transition`, no `atdd coach approve`. The operator runs those.
- No `gh issue create`, no `gh pr create` — prohibited by repo convention. Mint nothing at all
  this dispatch.
- No `--no-verify`, no force-push.
- Do not weaken, skip, or `xfail` any test to make a suite green.
- Do not run `atdd state migrate-layout` — it would touch every sibling worktree.
- The three dirty `.atdd/baselines/validation/*.yaml` are pre-existing. Leave them; do not
  commit them.
- If a command reports success, verify it wrote something before believing it.
- If you get blocked on a permission, **stop and report it**. Do not improvise an alternative
  route to the same effect.
