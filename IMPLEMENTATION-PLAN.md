# IMPLEMENTATION-PLAN.md — #1580 Harden the State Store against silent mass-deletion

Status: **PROPOSED — awaiting operator review. No code written yet.**
Branch/worktree: `feat/harden-store-against-silent-mass-deletion`

---

## 0. What I verified before planning (evidence, not assumption)

| # | Claim | Evidence |
|---|---|---|
| F1 | `read_projection` returns `{}` **silently** when the projection dir is missing | `src/atdd/state/projection.py:447-449` — `if not projection_dir.is_dir(): return documents` |
| F2 | `_replace_public_state` deletes every work_item not in that `{}` | `src/atdd/state/reconcile.py:363-366` |
| F3 | The clean-store reconcile path routes straight into that delete with **no** guard | `reconcile.py:554-564` → `hydrate_store` → `_replace_public_state` (`reconcile.py:337`) |
| F4 | `.atdd/state/` is gitignored, which covers `projection/` | `.gitignore:44`; `git check-ignore -v .atdd/state/projection/` → `.gitignore:44:.atdd/state/` |
| F5 | `events` **FK-CASCADEs** on object delete — a deleted object erases its own audit trail | `src/atdd/state/migrations.py:60` `FOREIGN KEY (object_uid) REFERENCES objects(uid) ON DELETE CASCADE` (same for `relationships` :46-47 and `external_refs` :73) |
| F6 | HEAD-moving hooks call `atdd state reconcile` unconditionally | `src/atdd/coach/templates/hooks/{post-merge,post-checkout,post-rewrite,pre-rebase}`, pinned by `tests/reconcile_local_store/test_m001_unit_001_*.py` |
| F7 | Live store today: **4 work_items**, 36 events, `store_metadata` holds only `dirty=clean` — **no `store_base_commit`** | read-only `mode=ro` query against `/Users/alecfokapu/Github/atdd/.atdd/state/state.sqlite` |

### F8 — the finding that changes the shape of Priority 1

The brief's P1.1 ("un-gitignore `.atdd/state/projection/` and commit it") is **necessary but cannot
work in this repo's actual layout**, and I want your decision before I write it.

`reconcile.projection_path(control_root)` is `control_root/.atdd/state/projection`
(`reconcile.py:235-236` + `projection.py:54`). In a flat-sibling worktree layout, `resolve_control_root`
anchors the control root at the **project root** — the parent of `main/` — not at any checkout
(`paths.py:194-218`, rule 1.5 at :286-299). Verified live:

- control root = `/Users/alecfokapu/Github/atdd/` — holds `.atdd/state/state.sqlite`, **no `projection/` dir at all**
- `git -C /Users/alecfokapu/Github/atdd rev-parse --show-toplevel` → `fatal: not a git repository`
- ~134 sibling worktrees share that one store

So the projection directory the shared store reconciles against **lives outside every git checkout**.
No `.gitignore` edit in this repo can ever make HEAD carry it, because it is not inside a repo.
`read_projection` will return `{}` forever, and F2 turns that into a full wipe every time.

The `.gitignore` fix is still correct and still required — it fixes the **single-repo / consumer-install**
layout, which is what ships to users. But for *this* project the doom-loop is closed only by the
fail-closed guards (P1.2), which is precisely why I am proposing to land those as the load-bearing fix
and treat the `.gitignore` change as the secondary half. It also means **P2 (ownership) is not
optional polish — it is the root cause** of F8, and the guards are what buy us the time to do P2 properly.

### Discrepancy to flag

`gh issue view 1580` does **not** contain the architect's correction. The body is the unmodified
`atdd author issue` boilerplate (generic "the gap exists today" table, train `0003-author-substrate`,
feature `author-issue-body`), and `comments: 0`. I am therefore planning against **BRIEF-1580.md** as
the authoritative requirements. If the correction exists somewhere else, point me at it before I code —
I do not want to build the wrong guard set.

### `atdd gate`

Ran clean (loaded CLAUDE.md `297712b704a37e71`, GEMINI.md, GLM.md; printed the issue convention).
One warning worth your attention: `⚠️ ATDD upgraded (3.106.0 → 4.21.0). Run: atdd sync && atdd init`.
I have **not** run `atdd sync`/`atdd init` — `init` installs hooks and touches the store, and I am not
touching the live store without your say-so.

---

## Priority 1 — stop the doom-loop

Three independent guards. Each fails closed, each is separately fault-injectable, and any one of them
alone would have prevented the incident. I want all three because F8 shows the failure had two
independent causes and I do not trust a single choke point.

### P1.a — `read_projection` stops lying about a missing directory

**File:** `src/atdd/state/projection.py`

Split the silent `{}` into a distinguishable outcome. Add `MissingProjectionError(ProjectionError)`
and a `read_projection(dir, *, require=False)` keyword — `require=True` raises when the dir is absent
rather than returning `{}`. Default stays `False` so `compact_archive`, `check_canonicality` and the
existing tests are untouched. Reconcile passes `require=True`.

Rationale: "the directory does not exist" and "the directory exists and is empty" are different facts
today collapsed into one value, and the collapse is half the bug.

### P1.b — degenerate-projection refusal + blast-radius threshold

**File:** `src/atdd/state/reconcile.py`

New exception `MassDeletionRefused(RuntimeError)` — same posture as `DirtyStoreError`: raised **before
any sqlite mutation**, carrying the counts and the remedy.

`_replace_public_state(store, projection_dir)` gains a guard pass before the delete loop:

```
existing   = store.objects.list(kind=WORK_ITEM_KIND)
incoming   = read_projection(projection_dir, require=True)
doomed     = [o for o in existing if o.uid not in incoming]
```

Refusals, in order:

1. **Empty projection vs populated store** — `not incoming and existing` → refuse, naming
   `len(existing)`. An empty projection never deletes a populated store, full stop.
2. **Blast radius** — `len(doomed) > MAX_ABSOLUTE (10)` **or** `len(doomed) / len(existing) > MAX_FRACTION (0.10)`
   → refuse, naming both numbers and the threshold that tripped.

Both thresholds land as module constants overridable by an explicit, *named* operator argument
(`allow_deletions=N`) threaded from a new `atdd state reconcile --allow-deletions N` flag. Deliberately
**not** an env var and **not** `--force`: the operator has to state the number they expect, so a wrong
number is still a refusal. This is not a bypass — it is the guard asking the operator to assert the
blast radius, and refusing if reality disagrees.

### P1.c — absence ≠ deletion (the structural fix)

**Files:** `src/atdd/state/reconcile.py`, `src/atdd/state/tombstone.py`

After P1.c, `_replace_public_state` **never deletes on absence at all**. Deletion requires the incoming
projection to carry an explicit tombstone for that uid:

- absent from projection → **no information** → object retained untouched
- present with `state: TOMBSTONED` → soft-delete (see P3.b)
- present with `state: ACTIVE` → hydrated as today

The tombstone record grows the provenance the brief requires — `actor`, `reason`, `source_generation`,
`prior_digest` (`object_digest()` of the pre-tombstone document) — added to `tombstone_record()` in
`tombstone.py:50-55` and to `FIELD_TYPES["tombstone"]` validation in `projection.py`.

**This makes P1.b unreachable in normal operation.** That is intentional and I want to be explicit
about it: P1.b becomes a defence-in-depth backstop for a future path that reintroduces absence-deletion.
I will keep P1.b's tests driving `_replace_public_state` through a seam that still exercises the
counting guard, so it does not rot into an untested stub — see "how each guard is proven to fail" below.

**Invariant cost, stated honestly:** the module docstring's I3
(`store == hydrate(projection @ base) + replay(overlay)`, `reconcile.py:8`) and
`_replace_public_state`'s own docstring both assert replace-not-merge. P1.c **weakens** that to
"replace, except that absence is not evidence of removal." The docstrings must be rewritten to say so —
I am not going to leave a comment claiming an invariant the code no longer holds. `check_canonicality`
is unaffected (it round-trips the projection, never the store).

### P1.d — `.gitignore`

**File:** `.gitignore` (line 44)

```
.atdd/state/
!.atdd/state/projection/
!.atdd/state/projection/**
```

Git will not descend into an excluded directory, so the negation of the parent path must come first —
I will verify with `git check-ignore -v` rather than assuming the pattern is right.

**What I will NOT do without your word:** generate and commit a projection. Per F8 the shared store's
projection dir is outside the repo, so `atdd state project` would have to be pointed at a control root
explicitly, and the only store holding real data is the live one. Generating a projection *from* the
live store is a read, which is safe — but committing 4 work_items as this repo's authoritative
projection is a data-shape decision, not a code fix. **Question 3 below.**

### P1.e — the reconcile entry point refuses earlier

**File:** `src/atdd/state/reconcile.py` (`reconcile()`, ~line 531)

Today the clean-store path delegates to `hydrate_store` (:554-564), so a hook-driven reconcile inherits
hydrate's guards and nothing else. Add the P1.b/P1.c check at the `reconcile()` boundary too, so the
refusal names *reconcile* in its message (the operator ran `atdd state reconcile`; telling them about
`hydrate` sends them down the wrong path).

---

## How each guard is proven able to FAIL

A guard with no failing test is a stub. Every one below is a test that **makes the guard fire** and
asserts the store is byte-identical afterwards — not merely that the happy path still passes.

All of these run against `tmp_path` stores built with the existing
`src/atdd/state/tests/reconcile_local_store/_helpers.py` fixtures. **No test touches the shared store.**
New files land in `src/atdd/state/tests/reconcile_local_store/`, following the existing
`test_<WMBT>_<layer>_<NNN>_<slug>.py` + URN-header convention.

| Guard | Fault injected | Asserted |
|---|---|---|
| P1.a missing dir | store with 3 work_items; `projection_dir` **deleted** | `MissingProjectionError`; `objects.list()` still 3; `store_base_commit` unmoved |
| P1.b empty projection | projection dir exists, **zero** `*.yaml`; store has 3 | `MassDeletionRefused`; message contains `3`; store unchanged |
| P1.b absolute threshold | store 30, projection carries 5 (25 doomed > 10) — via the counting seam | `MassDeletionRefused` naming `25` and `10`; store unchanged |
| P1.b fractional threshold | store 1000, projection 800 (200 doomed = 20% > 10%) | `MassDeletionRefused` naming the ratio; store unchanged |
| P1.b override is not a bypass | `--allow-deletions 5` against 25 doomed | still refused; the number the operator asserted is quoted back |
| P1.c absence ≠ deletion | store 3, projection carries 1, **no tombstones** | **no exception**; all 3 retained; the 2 absent ones untouched |
| P1.c tombstone does delete | projection carries `state: TOMBSTONED` + full provenance for 1 uid | that uid soft-deleted; other 2 untouched; provenance readable |
| P1.c malformed tombstone | tombstone missing `actor`/`reason` | refused by `validate_document`; nothing deleted |
| P1.d gitignore | — | `git check-ignore -v .atdd/state/projection/x.yaml` exits non-zero; `.atdd/state/state.sqlite` still ignored |
| **Regression: the incident itself** | end-to-end: temp repo, hooks installed, projection dir gitignored+absent, store populated, HEAD moved | reconcile **refuses**; work_items survive. This is the test that fails on today's `main`. |

The last row is the one I care most about — it reproduces the incident mechanically and is the
acceptance test for "this class of bug is closed."

---

## Priority 2 — ownership model (RECOMMENDATION, not implementation)

Per the brief I will not implement this until you pick. F8 is this decision showing up as a live outage.

**I recommend (b), with (a) as the interim.**

The observed layout is one mutable store at `/Users/alecfokapu/Github/atdd/.atdd/state/` shared by ~134
sibling worktrees, hydrating from whatever HEAD the worktree that ran the hook happens to be on. That
is a single mutable resource with 134 uncoordinated writers and no ordering — an older feature-branch
HEAD rolls the shared store backward and nothing notices, exactly as the brief predicts.

- **(b) single-daemon ownership** is the only option that actually fixes it: one owner reconciles the
  shared store against a *canonical default-branch generation* only; worktree hooks send a **notify**
  (an outbox row / a socket ping) and never open the shared sqlite for a hydrate. The store gets one
  writer and a monotonic generation, which is what makes "is this projection stale?" a decidable question.
- **(a) per-worktree store + overlay** is cheaper and I would take it as a stepping stone, but it
  multiplies the store by 134 and moves the consistency problem to merge time rather than removing it.

**Interim, and cheap enough that I would fold it into P1 if you agree:** since the shared control root
is not a git repo, `reconcile()` calling `gitstore.head(control_root)` on it is already incoherent. A
guard that **refuses to reconcile a shared, project-root-anchored store from a worktree HEAD at all**
is ~15 lines and removes the whole class immediately, ahead of any daemon work. Say the word and I add
it as P1.f.

Also in scope for P2 once you pick: a `repo_identity` + `generation` pair in `store_metadata`, so a
projection from the wrong repo or an ancestor generation is refused rather than applied. I would land
those keys in P1 (as inert metadata, written but only *read* by a warning) so the daemon work later has
its anchor already populated. Flagging rather than assuming — **Question 4.**

---

## Priority 3 — durability defaults (after P1 lands and is green)

Sequenced, each its own commit:

- **P3.a — three-way merge with identity/generation/digest guards.** `reconcile()` becomes base-aware:
  refuse on empty, stale, ancestor, or wrong-repo projections. Depends on the P2 decision for the
  generation semantics.
- **P3.b — soft-delete into quarantine.** New `quarantine` table (uid, kind, state, data, tombstone
  provenance, quarantined_at). Normal reconcile moves rows there; `atdd state compact` is the separate,
  approved hard delete. Restore path (`atdd state restore <uid>`) is part of this, not a follow-up —
  quarantine you cannot restore from is a slower delete.
- **P3.c — events must not FK-cascade (F5).** Migration dropping `ON DELETE CASCADE` on
  `events.object_uid` (SQLite: table rebuild). The audit trail must outlive its object — today the
  evidence of a deletion is destroyed by the deletion. `relationships` keeps its cascade (an edge to a
  gone object is meaningless); `external_refs` I would also decascade, since a provider link is
  evidence. Note there are already two live `trg_audit_delete_*` triggers in the shared store that are
  **not** in `migrations.py` — I want to know their provenance before I write a migration over them
  (**Question 5**).
- **P3.d — SQLite Online Backup API in `atdd state init`.** `conn.backup()` (not `shutil.copy2`) into a
  separately-retained checksummed location, with a **restore test** in CI — an untested backup is a
  hope. Note `backup_store()` (`reconcile.py:255`) currently uses `copy2` after a WAL checkpoint; it
  moves to the backup API too.
- **P3.e — migration backfill** so existing stores gain the quarantine table, the metadata keys, and
  the decascaded events on upgrade.

---

## Commit sequence (each ≤5 files, conventional, no `Co-Authored-By`)

1. `test:` the incident-regression test + the three refusal tests — **RED, failing on today's code**
2. `fix(state): refuse to hydrate a populated store from a missing or empty projection` (P1.a + P1.b)
3. `fix(state): absence in the projection is not evidence of deletion` (P1.c + tombstone provenance)
4. `fix(state): track the committed projection instead of ignoring it` (P1.d)
5. `refactor(state): correct the replace-not-merge docstrings to match the weakened invariant`
6. *(if approved)* `fix(state): refuse worktree-HEAD reconcile against a shared project-root store` (P1.f)

Then: `atdd pr 1580` → immediately de-keyword the body to `Refs #1580` → report. **I will not merge.**

---

## Questions I need answered before I write code

1. **The issue body has no architect's correction** (boilerplate only, 0 comments). Proceed against
   BRIEF-1580.md as authoritative, or is the correction somewhere I should read?
2. **P1.c changes a documented invariant** (replace-not-merge, I3). Confirmed acceptable? It is the
   right call, but it is a semantic change to the core of this module and I will not slip it past you.
3. **Do I generate and commit a projection** (P1.1 in the brief)? Given F8 the shared store's projection
   dir is outside the repo. Reading the live store to project from is safe; committing 4 work_items as
   this repo's authoritative projection is a data decision. My default if you say nothing: **do the
   `.gitignore` change only, commit no projection content.**
4. **P1.f** — add the shared-store/worktree-HEAD refusal now (~15 lines, closes the live class today),
   or hold it for the P2 decision?
5. **`trg_audit_delete_objects` / `trg_audit_delete_external_refs`** exist in the live store but not in
   `migrations.py`. Yours, from the incident response? I need to know before P3.c writes a migration
   over that table.

**No code will be written until you reply.**
