# #1742 — the second writer of `atdd:COMPLETE`, named

**Issue:** #1742 (child of program #1400)
**Date:** 2026-08-04
**Toolkit version investigated:** `atdd 4.38.6`
**Status:** investigation complete; no fix written

All `file:line` citations below were verified against **both** the worktree source and
the *installed* tree at
`~/.local/pipx/venvs/atdd/lib/python3.14/site-packages/atdd/`. The two are identical
line-for-line at every site cited. (atdd self-upgrades constantly, so this was checked
rather than assumed.)

---

## 1. Verdict, up front

The second writer is **`IssueManager._archive_github`**, at
`src/atdd/coach/commands/issue.py:988-994`, reached from
`src/atdd/coach/commands/issue_transition.py:97-99`.

It is a **genuine double-delivery — racing and currently lucky**, not benign idempotence.

The filer's hypothesis — that the §18 derived-COMPLETE split gives `COMPLETE` two
uncoordinated writers (the transition projection and an independent merge-to-main
derivation) — is **REFUTED**. See §6.

---

## 2. Reproduction — 9 of 9, terminal edge only

Reproduced independently on the filer's four (#1718, #1719, #1720, #1726), on the
operator's fifth (#1689), and on **four the filer did not name** — #1711, #1688, #1661,
#1632. Every one shows the identical four-event terminal shape; every non-terminal edge
is a single clean swap.

```
gh api "repos/afokapu/atdd/issues/<N>/timeline?per_page=100" --jq \
  '.[]|select(.event=="labeled" or .event=="unlabeled" or .event=="closed")
      |"\(.created_at) \(.event) \(.label.name // "-") by \(.actor.login)"'
```

Example, #1689 (note the `closed` event lands **65 minutes before** the duplicate):

```
2026-08-03T03:36:29Z closed    -              by afokapu
2026-08-03T04:41:56Z unlabeled atdd:REFACTOR  by afokapu
2026-08-03T04:41:58Z labeled   atdd:COMPLETE  by afokapu   <- writer 1
2026-08-03T04:42:01Z unlabeled atdd:COMPLETE  by afokapu   <- writer 2, remove half
2026-08-03T04:42:03Z labeled   atdd:COMPLETE  by afokapu   <- writer 2, add half
```

| issue | closed at | terminal swap | duplicate | close → duplicate gap |
|-------|-----------|---------------|-----------|----------------------|
| #1718 | 15:22:57  | 15:34:23/25   | 15:34:29/31 | 11 min |
| #1719 | 15:38:04  | 15:43:22/24   | 15:43:29/31 | 5 min |
| #1720 | 00:35:18  | 02:00:28/30   | 02:00:35/37 | **85 min** |
| #1726 | 09:09:10  | 09:09:43/44   | 09:09:47/48 | 38 s (`github-actions[bot]`, both writers) |
| #1689 | 03:36:29  | 04:41:56/58   | 04:42:01/03 | 65 min |
| #1711 | 01:50:40  | 02:00:45/48   | 02:00:51/52 | 10 min |
| #1688 | 04:52:56  | 04:56:43/44   | 04:56:48/49 | 4 min |
| #1661 | 02:39:34  | 03:43:43/45   | 03:43:49/51 | 64 min |
| #1632 | 23:16:35  | 23:33:35/36   | 23:33:40/41 | 17 min |

**All nine were already CLOSED before their terminal transition** — the merge closed
them. This matters: every one of the nine should have taken the already-archived early
return described in §4, and none did.

---

## 3. The second writer

`src/atdd/coach/commands/issue_transition.py:97-99` — `apply_transition` calls
`IssueManager.update()` (writer 1) and then, **only when the target is COMPLETE**, calls
`manager.archive()`:

```python
# COMPLETE auto-archives: close WMBTs + parent issue.
if status.upper() == "COMPLETE":
    arc_rc = manager.archive(issue_id=issue_id)
```

That single conditional is the **entire** reason only the terminal edge duplicates. It is
not a property of COMPLETE having two sources of truth.

`archive()` → `_archive_github` → `src/atdd/coach/commands/issue.py:988-994`:

```python
# Swap label to atdd:COMPLETE
try:
    labels = [l["name"] for l in issue.get("labels", [])]
    phase_labels = [l for l in labels if l.startswith("atdd:") and l != "atdd-issue"]
    if phase_labels:
        client.remove_label(issue_number, phase_labels)     # :993  <- unlabel COMPLETE
    client.add_label(issue_number, ["atdd:COMPLETE"])       # :994  <- label COMPLETE
except GitHubClientError as e:
    print(f"  Warning: Could not update labels: {e}")       # :995-996
```

This confirms the operator's lead exactly. It is **not** a bare "add label". It is a raw
remove-then-add swap computed from `(current, target)` with **no no-op short-circuit**,
which is why it fires with `current == target == COMPLETE`.

Critically, it **does not go through `_write_phase_label`** (`issue.py:1621-1677`), the
writer that `issue.py:1571-1573` calls "the sole authoritative `atdd:*` label write in the
codebase". It is a second, independent, raw writer.

The observed ~3-4 s gap between writer 1 and writer 2 is the three intervening `gh`
subprocess calls inside `_archive_github`: `get_issue` (`:962`), `get_sub_issues`
(`:973`), `close_issue` (`:985`).

---

## 4. Why the already-archived guard never fires — a casing bug

`_archive_github` opens with a guard that is *meant* to make all of this a no-op for an
already-closed issue, `src/atdd/coach/commands/issue.py:967-969`:

```python
if issue.get("state") == "closed":
    print(f"#{issue_number} is already closed.")
    return 0
```

`client.get_issue` shells out to `gh issue view --json number,title,state,labels,body`
(`src/atdd/coach/github.py:601-608`). **`gh` returns the state uppercase.** Verified live:

```
$ gh issue view 1689 --repo afokapu/atdd --json number,state
{"number":1689,"state":"CLOSED"}
```

`"CLOSED" != "closed"`, so **the guard never fires** — for any issue, ever.

The casing was known to the author. The same field is compared correctly **244 lines
earlier in the same file**, `src/atdd/coach/commands/issue.py:723`:

```python
if (issue.get("state") or "").upper() == "CLOSED":
```

So this is a slip at `:967`, not a misunderstanding of the API.

Combined with §2: all nine samples were closed before their terminal transition, so all
nine should have returned at `:968` without touching a single label.

---

## 5. In-process reproduction of the mechanism

The mechanism was confirmed by execution, not by inspection. `_archive_github` was driven
with a mocked client returning **exactly** what `gh` returns (`state: "CLOSED"`, labels
already carrying `atdd:COMPLETE` from writer 1):

```python
client.get_issue.return_value = {
    "number": 1689, "state": "CLOSED",
    "labels": [{"name": "atdd-issue"}, {"name": "atdd:COMPLETE"}],
}
client.get_sub_issues.return_value = []
rc = IssueManager()._archive_github("1689")
```

Result:

```
  Closed parent #1689
Archived #1689: closed 0 sub-issues, 0 total
rc = 0
close_issue  called: [call(1689)]
remove_label called: [call(1689, ['atdd:COMPLETE'])]
add_label    called: [call(1689, ['atdd:COMPLETE'])]
```

The early return is skipped, and the remove/add pair is issued with
`current == target == COMPLETE` — writer 2, exactly as observed on the wire.

---

## 6. The §18 hypothesis is REFUTED

The filer proposed that `COMPLETE` is the only phase with two sources of truth — the
transition projects the label, and an independent merge-to-main derivation concludes
`COMPLETE` and projects it too — making the duplicate a structural consequence of the §18
split. It is not. Three independent refutations:

**(a) Same process, same call stack.** Writer 2 is a synchronous call from writer 1's own
orchestrator, `issue_transition.py:99`, ~3 s later. There is no second derivation path
involved. The COMPLETE-only conditional at `issue_transition.py:98` — not §18 — is what
makes the terminal edge special.

**(b) The timing rules out merge-derivation.** On #1720 the merge/close landed at
`00:35:18` and the duplicate fired at `02:00:35` — **85 minutes later**, 3 seconds after a
manual CLI transition. Same shape on #1661 (64 min), #1689 (65 min), #1632 (17 min). A
writer triggered by merge-to-main would have fired at merge time, not an hour later on a
human's keystroke. And on #1726 writer 2 is `github-actions[bot]` — the *same* actor as
writer 1, not a second independent path.

**(c) The merge-time label writer was deleted and provably has not regrown.** #1452
removed the `post-merge-lifecycle.yml` label-swap step;
`test_post_merge_lifecycle_authors_no_phase_label`
(`src/atdd/coach/validators/test_phase_label_projection_only.py:166-185`) asserts it
stays gone, and it is green.

The filer's two §18 citations both still hold at the stated lines in 4.38.6 —
`src/atdd/state/evidence.py:20` ("COMPLETE is derived, never stored") and
`src/atdd/state/evidence.py:253` ("may never be stored in the projection"). They are
simply not implicated in this defect.

**The §18 ruling is not reopened and is not at fault.** Its implementation does not have
two writers. `archive()` does.

---

## 7. Why the guard built to prevent exactly this misses it

`coach.phase-label.projection-only` exists specifically to stop a second `atdd:*` writer
from regrowing (#1452, after #1434 proved deletion alone was insufficient). It is green.
The reason is a **granularity mismatch**.

The rule is **method-scoped**. `test_phase_label_projection_only.py:9-11` states
"`IssueManager.update` is its sole authoritative writer".

The exemption is **file-scoped**,
`src/atdd/coach/validators/test_phase_label_projection_only.py:59-62`:

```python
# The ONLY code path allowed to write an `atdd:<PHASE>` label.
AUTHORITATIVE_WRITER = "src/atdd/coach/commands/issue.py"
```

and the whole file is skipped at
`src/atdd/coach/validators/test_phase_label_projection_only.py:102`:

```python
if rel_path == AUTHORITATIVE_WRITER or _is_test_path(rel_path):
    continue
```

An exemption written to cover **one method** is covering **the entire file that method
lives in** — and `_archive_github` lives in that file.

Driving the scanner over that same file's text under a non-exempt path finds **two**
writers:

```
issue.py:994   raw python write of an atdd:<PHASE> label   <- _archive_github    (UNSANCTIONED)
issue.py:1652  raw python write of an atdd:<PHASE> label   <- _write_phase_label (sanctioned)
```

(Only the `add` half of `_archive_github`'s swap is flagged; `:993` passes `phase_labels`
as a variable and carries no `atdd:` token for `_ATDD_LABEL_TOKEN` at
`test_phase_label_projection_only.py:68` to match. One violation is sufficient.)

The allowlist-integrity test that is supposed to keep the exemption honest,
`src/atdd/coach/validators/test_phase_label_projection_only.py:199-214`, asserts only
that the exempt file **contains** a phase-label write:

```python
assert "_write_phase_label" in text and "add_label" in text
```

It never asserts the file contains **exactly one**. So the exemption widened into a hole
and the sweep still passes green — which is the precise failure mode that test's own
docstring (`:188-196`) warns about.

Confirmed by execution: `pytest test_phase_label_projection_only.py
test_r005_unit_001_no_raw_phase_label_writers.py` → **12 passed**, with the raw writer
sitting at `issue.py:993-994` the whole time.

---

## 8. Verdict — genuine double-delivery, racing and currently lucky

Not idempotence by design, and not idempotence by construction. Four reasons, in
descending order of cost:

**(1) There is a real window in which the issue carries no phase label at all.**
`remove_label` (`issue.py:993`) and `add_label` (`issue.py:994`) are two separate API
calls. Measured on the wire, the gap is 1-2 s — e.g. #1720, `02:00:35` unlabeled →
`02:00:37` labeled. During that window `_read_phase_labels` (`issue.py:1773-1779`)
returns `"UNKNOWN"` and `_read_current_github_phase` (`coach.py:787-806`) returns `None`.
The window is real and observable; there is *no evidence yet* that any reader has actually
sampled it, and that distinction is deliberate — the window's existence is proven, its
having been hit is not.

**(2) A failure between the two halves is silently reported as success — the #1621
failure class, reintroduced.** If `remove_label` lands and `add_label` is refused,
rate-limited or dropped, the `except GitHubClientError` at `issue.py:995-996` downgrades
it to `print("  Warning: Could not update labels: ...")` and `_archive_github` still
returns **0** (`issue.py:1015`). `issue_transition.py:100-101` only warns on non-zero, so
`apply_transition` returns the re-enter code and the transition reports success over an
issue left with **no phase label**. Contrast the sanctioned writer `_write_phase_label`
(`issue.py:1642-1676`), which tracks what came off, diagnoses *which* half was refused,
and returns `False` — precisely because #1621 was about a half-applied transition
reporting green.

**(3) Read-modify-write with no compare-and-swap.** Labels are read at `issue.py:962` and
written at `issue.py:993`, ~3 s and three network round-trips later. Anything that
changed the phase label in that window is silently reverted to `COMPLETE`.

**(4) It bypasses the phase machine, the train gate and the COMPLETE gates.** This is the
identical indictment that `_swap_phase_label`'s own docstring makes of the code #1452
deleted (`src/atdd/coach/commands/coach.py:812-825`: "It stamped a projection while
`objects.state` stood still, and it did so without the phase machine, the train gate or
the COMPLETE gates ever running"). The same defect regrew in a different function, inside
the one file the guard does not look at.

It has been harmless so far for two narrow reasons: both halves have happened to succeed
every time, and nothing has sampled the gap. Neither is a property of the code, and
neither survives a slow or rate-limited provider.

---

## 9. Scope boundaries observed

- **§18 not reopened.** The derived-COMPLETE ruling is #1400's and stands. This finding
  concerns its implementation, and clears it: the ruling is not the cause.
- **Not folded into #1655/#1711.** Those are *stranded* deliveries. This is a *duplicate*
  delivery, with an independent root cause (a casing slip plus a file-granular exemption).
  Opposite failure modes; kept separate.

---

## 10. Open decisions for the operator — no fix written

Per the investigation-first instruction, no fix has been implemented. Two parts, and both
want an explicit decision:

1. **The writer.** `_archive_github`'s label swap is *redundant* on the transition path —
   `IssueManager.update` (`issue.py:1574`) has already projected `atdd:COMPLETE` before
   `archive()` runs. The narrow fix is to correct the casing at `issue.py:967`; the
   correct fix is likely to delete the swap at `issue.py:988-994` entirely and let
   `archive` do only what its name says (close sub-issues + parent). **Requires checking
   whether any non-transition caller of `atdd archive` depends on the swap** — the
   deprecated `atdd archive <N>` shim (`cli.py:2269-2270`) is one such path.
2. **The guard.** Make the exemption method-scoped, or have the allowlist-integrity test
   at `test_phase_label_projection_only.py:199` assert the exempt file holds *exactly one*
   writer. Without this, a third regrowth is unguarded — and #1434 already proved once
   that deletion without a guard does not hold.

Nothing in this investigation required `atdd coach transition`, `atdd coach approve`, or
`atdd upgrade`.
