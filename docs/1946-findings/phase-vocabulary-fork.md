# #1946 — investigation: the phase-vocabulary fork

Read-only pass on `main` at `b83f4cf8`. No branch, no plan artifacts.
Every claim below was executed or grepped, not inferred.

## Summary of what changes about the issue as written

| Issue says | Actually |
|---|---|
| four phase vocabularies | **six**, and the fifth (`coach.core.types.Phase`) is already a correct copy |
| "resolve the MERGED vs OBSOLETE disagreement" | `MERGED` is **unreachable dead code**; there is no live disagreement to arbitrate |
| `Phase("DISCOVERY")` raises in the coach runtime | true, **and** it raises earlier, in `load_conventions`, off a *different* enum |
| derive `Phase` + `TRANSITION_TABLE` from the convention | necessary, **not sufficient** — nine more hand-maintained phase tables survive |

The issue's diagnosis is right. Its scope is about half the defect.

---

## 1. The vocabularies

Executed probe (`python3 -c` against `src/`):

```
handlers.Phase  : INIT PLANNED RED GREEN SMOKE REFACTOR COMPLETE BLOCKED MERGED
core.types.Phase: INIT PLANNED RED GREEN SMOKE REFACTOR COMPLETE BLOCKED OBSOLETE

handlers.Phase('OBSOLETE') -> RAISES ('OBSOLETE' is not a valid Phase)
core   .Phase('MERGED')   -> RAISES ('MERGED' is not a valid Phase)
```

| # | Source | Vocabulary | Derived? |
|---|---|---|---|
| 1 | `coach/conventions/phase_machine.convention.yaml` | INIT…COMPLETE, BLOCKED, **OBSOLETE** (9) | — *(source of truth)* |
| 2 | `coach/handlers/state_machine.py:34` `Phase` | INIT…COMPLETE, BLOCKED, **MERGED** (9) | ❌ literal |
| 3 | **`coach/core/types.py:23` `Phase`** | INIT…COMPLETE, BLOCKED, **OBSOLETE** (9) | ❌ literal, but **agrees** |
| 4 | `state/projection.py:62` `PHASES` | 8 (no COMPLETE) | ❌ literal, tied by test |
| 5 | `state/evidence.py:69` `PHASE_LADDER` | 7 (spine only) | ❌ literal, tied by test |
| 6 | bare-string sets in command modules | assorted | ❌ literal, untied |

**Two `Phase` enums live in the same package** and each raises on the other's ninth
member. That is the defect in one line.

### Why the fork went unnoticed for so long

Both are `str` mixins, so they interoperate *by value*:

```
H.COMPLETE == C.COMPLETE            -> True
H.COMPLETE in {C.COMPLETE, C.OBSOLETE} -> True
H.COMPLETE is C.COMPLETE            -> False
```

Equality and set membership succeed across the two classes. Nothing fails until
someone names a member the other side lacks. The fork is silent by construction.

---

## 2. Consumer map

### `handlers.state_machine` — the forked one (the live path)

| Consumer | Imports | Uses |
|---|---|---|
| `coach/commands/coach.py:55` | `Phase`, `PLANNED_PATH`, `StateMachine`, `TRANSITION_TABLE`, `can_transition`, `initialize_state_machine` | re-exports **all** in `__all__` |
| `coach/commands/coach.py:723` | `Transition`, `can_transition` | function-local, cold-start advance |
| `coach/commands/resume.py:40-43` | via `commands.coach`: `PLANNED_PATH`, `Phase`, `can_transition` | `drive_to_complete` walk |
| `coach/handlers/watcher.py:25` | `Phase`, `can_transition`, … | `_PHASE_TRAILER_MAP`, `_ADVANCE_FROM` |
| `coach/handlers/validator_dispatch.py:24` | `Phase` | `_SRC_TO_VALIDATOR_PHASE` |
| `coach/handlers/__init__.py:6` | all of it | re-export surface |
| `handlers/observer.py`, `handlers/decisions.py` | `CoachContext`/`HandlerResult`/`Transition` only | **no `Phase`** |

Plus ~18 test modules.

### `coach.core.types.Phase` — the convention-shaped one

| Consumer | Uses |
|---|---|
| `coach/core/__init__.py:34-45` | `_TERMINAL_PHASES = {COMPLETE, OBSOLETE}`, `_NON_FORWARD_TARGETS = {BLOCKED, OBSOLETE}`, `_MERGE_ELIGIBLE_PHASES` |
| `train/persistence.py:135,139` | `_phase_machine_from_data` — **coerces every YAML phase name through this enum** |
| `train/persistence.py:686,759` | session status |
| `train/types.py:19` | `TransitionDecision` |

### `phase_edges.phase_machine()` — the only true derivation

`coach/gate/phase_edges.py` reads the YAML, has **no hardcoded fallback**, and raises
`PhaseMachineUnavailable` rather than degrading. `coach/validators/test_required_label_set.py:60`
builds the GitHub label set from it:

```python
return tuple(f"atdd:{phase}" for phase in sorted(phase_machine()))
```

So the valid label set contains **`atdd:OBSOLETE` and not `atdd:MERGED`** — derived,
today, from the convention. The runtime enum contradicts the label taxonomy it ships with.

---

## 3. `MERGED` is dead

`Phase.MERGED` exists in the enum, in `TRANSITION_TABLE[COMPLETE]`, and at the tail of
`PLANNED_PATH`. **No production path can reach it.**

- `coach.py:607` `_COLD_START_ADVANCE_FROM` stops at `REFACTOR: COMPLETE`.
- `coach.py:615` `_PHASE_TRAILER_MAP` has no `MERGED` key.
- `watcher.py:59` `_ADVANCE_FROM` stops at `REFACTOR: COMPLETE`.
- `resume.py:256-258` explicitly refuses to walk into it:
  ```python
  # Stop walking past COMPLETE — MERGED is owned by the
  # PR-merge handler, not the per-issue resume runner.
  if next_phase == Phase.MERGED:
      break
  ```
  …and that PR-merge handler assigns no phase. `auto_phase.py:39` `_NEXT_PHASE` tops out
  at `"REFACTOR": "COMPLETE"`.
- No assignment of `Phase.MERGED` exists anywhere in `src/`. Grep for it returns only:
  the enum definition, the two table entries, `PLANNED_PATH`, the `resume.py` guard,
  and three tests that assert the enum's own shape
  (`test_d001_unit_001_state_machine_skeleton.py:35,55,63,71`).

The live notion of "merged" is a **PR state, not an issue phase**:

```python
# coach/core/__init__.py:205
if evidence.current_phase is Phase.COMPLETE and pr is not None and pr.state != "MERGED":
```

`coach/core/types.py:108` types it as `state: Literal["OPEN", "MERGED", "CLOSED"]` on the
PR. `github.py:601` and `merge_cascade.py:361` read the same PR field. And
`state/projection.py:66-70` settles the question of authority:

> `COMPLETE` is derived from merge-to-main (spec §18 decision 1): it has no legal
> projection document.

**Conclusion: there is nothing to arbitrate.** `MERGED` is not a rival name for
`OBSOLETE` — they sit on different axes (a terminal vs. an escape). `MERGED` is a
vestigial ninth enum member from the J1 skeleton (`state_machine.py` docstring: "All
logic is unchanged from J1 (issue #496)") that the merge design later routed around.
Deriving the enum from the convention **deletes it for free**.

---

## 4. `OBSOLETE` is invisible — but it degrades, it does not crash

Worth being precise, because the issue overstates the blast radius.

An `OBSOLETE` issue does not raise in `resume.py`. `_phase_index` (`resume.py:106-116`)
returns `-1` for any phase not on `PLANNED_PATH`, and the caller treats `-1` as "BLOCKED
or unknown; leave the phase as-is and continue" (`resume.py:242-247`). So `OBSOLETE` is
silently **conflated with `BLOCKED`** — the same handling, no diagnostic, no record that
a terminal was mistaken for a recoverable escape.

The loud failure is on the other enum. Adding `DISCOVERY` to the convention raises at
`train/persistence.py:135` (`_phase_machine_from_data` → `core.types.Phase(name)`) — i.e.
**convention loading itself fails**, before the coach runtime is ever reached. The issue
attributes the raise to `handlers.Phase`; that one raises too, but second.

---

## 5. The scope the issue misses: nine more hand-maintained tables

"A phase added to the convention is visible with no Python edit" is not achieved by
deriving `Phase` and `TRANSITION_TABLE`. Adding `DISCOVERY` today requires edits to:

| # | File | Table |
|---|---|---|
| 1 | `coach/handlers/state_machine.py:34` | `Phase` |
| 2 | `coach/handlers/state_machine.py:55` | `TRANSITION_TABLE` |
| 3 | `coach/handlers/state_machine.py:75` | `PLANNED_PATH` |
| 4 | `coach/core/types.py:23` | `Phase` |
| 5 | `coach/commands/coach.py:607` | `_COLD_START_ADVANCE_FROM` |
| 6 | `coach/commands/coach.py:615` | `_PHASE_TRAILER_MAP` |
| 7 | `coach/handlers/watcher.py:49` | `_PHASE_TRAILER_MAP` |
| 8 | `coach/handlers/watcher.py:59` | `_ADVANCE_FROM` |
| 9 | `coach/handlers/validator_dispatch.py:35` | `_SRC_TO_VALIDATOR_PHASE` |
| 10 | `coach/commands/auto_phase.py:39` | `_NEXT_PHASE` |
| 11 | `coach/runtime/dashboard.py:42,47` | `PHASE_ORDER`, `PHASE_RGB` |
| 12 | `coach/commands/issue_lifecycle.py:33,99` | `_TERMINAL_STATUSES`, `_NextAction` |
| 13 | `state/projection.py:62,70` | `PHASES`, `ARCHIVED_PHASES` |
| 14 | `state/evidence.py:69,79` | `PHASE_LADDER`, `EVIDENCE_POLICY` |

Items 5–8 and 10 are all the same fact — *the spine's successor function* — written five
times. Items 13–14 are already tied to the convention by
`state/tests/test_phase_ladder_matches_projection_phases.py`, which is the **existing
model for the fix** and should be extended rather than duplicated.

---

## 6. Recommendation

### 6.1 On MERGED vs OBSOLETE

**Delete `MERGED` from the phase vocabulary. Do not add it to the convention.**

Rationale, in the order that matters:

1. It is unreachable — no production write, and the one walker that could reach it
   refuses by design.
2. The concept it names already has a home: `PullRequest.state`, typed
   `Literal["OPEN","MERGED","CLOSED"]` in `core/types.py:108`, read by `core/__init__.py`,
   `github.py`, `merge_cascade.py`.
3. Promoting it to the convention would mint an `atdd:MERGED` GitHub label (via
   `test_required_label_set.py:60`) for a phase nothing can set — a new fork, in the
   direction of more surface.
4. `projection.py:66-70` states the design position outright: completion is derived from
   merge-to-main and has no projection document. An issue phase for "merged" contradicts it.

The cheapest correct framing: **the fix removes a phase rather than reconciling two.**
`resume.py:256-258` loses its guard (the walk already stops at `COMPLETE` via the
`while current != Phase.COMPLETE.value` condition), and `test_d001_unit_001` loses four
assertions about an enum member that should not exist.

### 6.2 On the derivation

**Collapse to one enum first, derive second.** Two steps, in this order:

1. **`handlers.state_machine` stops defining `Phase`** and re-exports
   `coach.core.types.Phase`. That single move deletes `MERGED`, admits `OBSOLETE`, and
   removes vocabulary #2 — with no new machinery, because #3 already matches the
   convention exactly. `TRANSITION_TABLE` and `PLANNED_PATH` then derive from
   `phase_edges.phase_machine()` (which already exists, already reads the YAML, and
   already fails closed).
   - Watch the import direction: `handlers` → `core.types` is new. `train.persistence`
     already imports `coach.core.types`, and `handlers/observer.py` +
     `handlers/decisions.py` import no `Phase` at all, so the blast radius is the five
     modules in §2.
   - `PLANNED_PATH` should be the convention's **spine**, computed exactly as the
     existing drift test's `spine` fixture computes it
     (`test_phase_ladder_matches_projection_phases.py:64-81`) — walk each phase's single
     non-escape target. Reuse that walker; do not write a second one.

2. **`core.types.Phase` is the remaining literal.** It agrees today, and it fails loudly
   (at `load_conventions`) rather than silently, so it is the acceptable stopping point
   for this issue. If it is to be derived too, that is a separate change with a real cost
   — a dynamically-built enum loses static typing across `train/`, `state/`, and every
   `Phase.X` reference. **Recommend: leave it literal, and pin it with a drift test**
   (see 6.3). Note this explicitly in the issue's Out-of-Scope so it is a decision rather
   than an omission.

### 6.3 On the drift test

The issue asks for "a drift test tying all four phase vocabularies together." There are
six, and one already exists.

**Extend `state/tests/test_phase_ladder_matches_projection_phases.py` rather than adding
a sibling.** It already loads the convention, already computes the spine, already
encodes `ESCAPES = {"BLOCKED", "OBSOLETE"}`, and already ties #1, #4, #5. Add:

- `set(core.types.Phase) == set(convention phases)` — catches a literal enum drifting,
  and is the assertion that would have caught this bug.
- `set(handlers.Phase) == set(core.types.Phase)` — trivially true once §6.2 step 1 lands,
  and the guard against re-forking.
- `TRANSITION_TABLE` edges `==` the convention's `transitions_to`, both directions.
- `PLANNED_PATH == spine` — reusing the fixture.
- The successor maps (§5 items 5–8, 10) agree with the spine's successor function. This
  is the assertion that turns "five copies of one fact" into a checked invariant, and it
  is worth more than the enum assertions.

### 6.4 Suggested edits to the issue body before PLANNED

- **Problem Statement** — record that there are two `Phase` enums in `atdd.coach`, name
  `core.types.Phase` as already-correct, and note the `str`-mixin equality that makes the
  fork silent.
- **Vocabulary table** — six rows, not four; mark which are derived and which are
  already tied by a test.
- **In Scope** — add "collapse `handlers.Phase` onto `core.types.Phase`" and "derive the
  per-phase successor maps in `coach.py`, `watcher.py`, `auto_phase.py` from the spine."
- **Out of Scope** — add "deriving `core.types.Phase` itself (stays a literal, pinned by
  drift test)" with the typing rationale.
- **Done-when** — replace "resolve the MERGED vs OBSOLETE disagreement" with "`MERGED` is
  removed from the phase vocabulary; merge-ness is read from `PullRequest.state` only."
- **Root Cause** — `state_machine.py` is the J1 skeleton (#496); `MERGED` predates the
  PR-based merge design that `projection.py` §18-decision-1 and `core/__init__.py:205`
  now implement. #888 de-duplicated the docs copies and left both Python ones.

---

## 7. Lab measurements (added after the fact — see §8)

Four arms, each a disposable clone of `main` at `4f9e0f54`, each running the full
`src/atdd/coach` suite unfiltered, each verified to import the clone's own `src/`
rather than the pipx install.

| Arm | Mutation | New failures vs baseline |
|-----|----------|--------------------------|
| A baseline | none | — (73 failures) |
| C control | `COMPLETE` removed from `TRANSITION_TABLE` + `PLANNED_PATH`, enum member kept | **5** |
| B partial | `MERGED` removed from enum + both tables | **19** |
| D complete | B, plus the `resume.py` guard the fix deletes anyway | **10** |

**The control exists to calibrate.** `COMPLETE` is reachable by construction, so
making it unreachable must produce failures if this suite can detect reachability
at all. It produces 5 — all resume/replay tests. The instrument is sensitive.

**Arm D is the answer.** All 10 remaining failures are test files carrying
hardcoded `MERGED` literals:

- `test_d001_unit_001` (4) — asserts the enum's own shape, incl. `all_nine_states`
- `test_J3_integration_001` (5) — `PLANNED_PATH_TRANSITIONS`, a literal list in the
  test file ending `("COMPLETE", "MERGED")`, NOT read from production `PLANNED_PATH`
- `test_r002_unit_001` (1) — `stop_set = {COMPLETE, MERGED, BLOCKED}`

Every resume and durable-decisions test — `R001_integration_001/002`,
`R001_smoke_001`, `J3_integration_002/003` — **passes**. Those are the paths that
would break if anything reached `MERGED`. The lifecycle runs start to finish
without it.

### What this changes about §3's claim

§3 said `MERGED` is "unreachable dead code". Measured, the honest statement is
narrower: **`MERGED` has no runtime producer.** It has dangling references — one
production line (`resume.py:257`, whose own comment says the phase belongs to the
PR-merge handler) and three test fixtures. Deleting it is safe, but "nothing
references it" was never true and grep was the wrong instrument for the question.

### An eighth vocabulary

`test_J3_integration_001.PLANNED_PATH_TRANSITIONS` is a hardcoded copy of the
planned path inside a test. §1 counted six; §5's table found a seventh in the plan
layer (the feature's `value_objects` rationale). This is the eighth.

### Two other measurements

- **No import cycle.** A fresh interpreter importing `phase_edges` pulls in 4 `atdd`
  modules, none of them `handlers.state_machine`. The new import edge is safe.
- **The enum swap is behaviourally inert.** 15-way differential probe of
  `(str, Enum)` vs `StrEnum` — `str`, f-string, `%`, `format`, `json.dumps` as value
  and as key, concatenation, both equality directions, hash-equality with `str`,
  sort order, pickle, identity on construction, `.value` type, `repr`. All 15
  identical. They differ only in membership.

## 8. Three inert instruments, recorded because the result nearly shipped

This section is the point of §7, not an aside. Three successive measurements were
broken, and each produced a tidy, plausible, WRONG answer:

1. **`-m "not platform"` deselected 1808 tests** — over half the suite, including all
   8 of `test_d001_unit_001`, the tests guaranteed to detect the mutation. Result:
   "identical to baseline, MERGED removal breaks nothing." Caught only by noticing
   the known-detectable assertions could not have run.
2. **The first control renamed `COMPLETE`**, breaking module-level references and
   aborting collection in 5.9s. No number at all — and it was not matched to the
   treatment, which changed tables rather than the symbol.
3. **`tail -60/-80` truncated every failure list** (55 of 75, 55 of 94, 77 of 83).
   The diff over three differently-truncated lists produced a clean "control 25,
   E2 1" that fit the thesis perfectly and was pure artifact. The underlying totals
   said the opposite.

Countermeasures now in the method: a positive control matched to the treatment; an
in-tree probe asserting which `atdd` the runner imports and what vocabulary it sees;
and a captured-vs-reported assertion so a truncated capture announces itself.

This is the same defect class as #1547 (validators provably inert) and #1925 (every
metric acceptance reports PASS against a threshold it never compared). An experiment
that cannot fail is not evidence.
