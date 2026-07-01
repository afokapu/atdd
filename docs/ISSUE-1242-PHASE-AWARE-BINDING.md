## Issue Metadata

| Field | Value |
|-------|-------|
| Date | `2026-06-29` |
| Status | `PLANNED` |
| Type | `implementation` |
| Branch | `feat/phase-aware-validator-binding` |
| Archetypes | tester |
| Train | `0001-self-compliance-validate` |
| Feature | `feature:govern-lifecycle:phase-aware-validator-binding` |

---

## Scope

### In Scope

- Make the **forward pass** of `test_repo_validator_binding.py::test_validator_binding_is_bidirectional` phase-aware: an acceptance that declares `harness.type` but has no anchored test is only a violation **once its owning issue has reached the phase at which the test is due** (RED). Acceptances whose owning issue is still at **INIT or PLANNED** are exempt, because their tests are not authored until the RED transition.
- Add a small, shared, testable helper that maps an acceptance → its owning issue's **current lifecycle phase**, read from the authoritative `.atdd/manifest.yaml` `sessions[]` (the same source the #1168 State Store imports). Mechanism + rationale documented in **Decisions**.
- Add a phase-ordering comparison grounded in `src/atdd/coach/conventions/phase_machine.convention.yaml` (`INIT < PLANNED < RED < GREEN < SMOKE < REFACTOR < COMPLETE`) — do **not** fork a second phase order.
- New plan artifacts under the existing **`govern-lifecycle`** wagon: feature `phase-aware-validator-binding` + WMBT `E057` (5 acceptances) + anchored tests.

### Out of Scope

- **Weakening the invariant.** From RED onward the requirement holds *exactly* as today. This change only *relaxes* the pre-RED window (INIT/PLANNED); it never relaxes RED+.
- **The reverse pass.** Orphan-test detection (a test header naming an `acc:*` URN that resolves to no acceptance) is unchanged and stays phase-blind.
- **Forking #1168.** We read the issue's current phase from the authoritative manifest source; we do not introduce a competing phase store or a new phase vocabulary.
- **Other substrate-enforcement validators** (measurability, declare-phase, disposition, metric-implementation, live-smoke). Untouched.
- **Retiring `ATDD_ALLOW_SUBSTRATE_BACKLOG`.** That migration env-var stays; this issue removes the *need* to reach for `atdd emergency` on legitimate PLANNED pushes, not the backlog escape hatch.

### Dependencies

- **#1168 (State Store)** — owns lifecycle/phase as source of truth. This issue reads phase from the manifest (State Store's import input) and is forward-compatible: when the State Store exposes a stable, guaranteed-populated `plan-file/issue → phase` read API, the helper swaps its single body without touching the validator. See **Decisions #2**.
- **#1238 / #1223** — mid-RED issues that currently rely on the *present* (phase-blind) gate having anchored tests. This change must land **after** they push and must not retroactively break their now-present tests. See **Notes → Review Log, Pass 2**.

---

## Context

### Problem Statement

| Aspect | Current | Target | Issue |
|--------|---------|--------|-------|
| Forward-pass trigger | Fires for **every** acceptance with `harness.type` and no anchored test, **unconditionally** — never consults phase | Fires only once the owning issue has reached **RED+** | A brand-new plan-only issue at **PLANNED** has authored acceptances but no tests yet (tests are written at RED), so the gate blocks its first push |
| Operator workaround | Reach for `atdd emergency` to push the PLANNED commit | No bypass needed — the gate is correctly phased | `emergency` is the prohibited compliance-bypass of last resort; the gate manufactures a false positive that *forces* it |
| Phase data | `_acceptance_walker` already exposes `acceptance_phase()` + `has_harness_type()`, but the forward pass ignores the **issue's** phase | Forward pass maps acceptance → owning issue → current phase | The data to phase the check exists; the validator just never asked "is this test due yet?" |

### User Impact

The ATDD lifecycle authors acceptances at **PLANNED** (planner/tester define the WMBTs) and writes their anchored tests at **RED**. The bidirectional-binding gate runs at pre-push and repo-wide. So the very first push of a freshly-planned, plan-only issue — the PLANNED commit that contains the new `plan/` acceptances and *nothing else* — is rejected: the new acceptances declare `harness.type` but their tests legitimately do not exist yet. The operator's only escape today is `atdd emergency`, which the project forbids as a compliance bypass. The gate thus penalizes correct lifecycle sequencing and trains operators to bypass.

### Root Cause

`collect_violations()` forward pass (`test_repo_validator_binding.py`, ~L122–147) treats "declares `harness.type` and has no anchored test" as a one-way-binding violation with no temporal qualifier. The bidirectional invariant is correct *as an end-state*, but it is being enforced at a point in the lifecycle (PLANNED) **before** the test is due (RED). The check needs a notion of "is the owning issue past the planning window?" — which is exactly the issue's current lifecycle phase, available in `.atdd/manifest.yaml` `sessions[].status`.

---

## Architecture

### Graph Context

- **Wagon:** `wagon:govern-lifecycle` (dir `plan/govern_lifecycle/`), theme `commons`.
- **Train:** `0001-self-compliance-validate` (this wagon is the train's `primary_wagon`).
- **Feature:** `feature:govern-lifecycle:phase-aware-validator-binding` (new; sibling of `hermetic-integration-execution-kind`, `live-smoke-execution-enforcement`, `enforce-smoke-refactor-phase-substrate` — the acceptance-violation substrate family).
- **WMBT:** `wmbt:govern-lifecycle:E057`.
- **Rule under refinement:** `tester.acceptance-violation.validator-binding-must-be-bidirectional` (node: `src/atdd/tester/conventions/nodes/tester.acceptance-violation.validator-binding-must-be-bidirectional.convention.yaml`). The rule **statement and binding are unchanged** — only the validator's enforcement *timing* is refined. No new rule_id is introduced.

### Mirror Across Agents

| Agent | Current state | Target state | Action |
|-------|---------------|--------------|--------|
| planner | Authors acceptances at PLANNED with `harness.type`; no signal that the test is not yet due | Same authoring; no change required | none |
| tester | `test_repo_validator_binding.py` forward pass is phase-blind; `_acceptance_walker.py` exposes phase/harness helpers but not an owning-issue-phase lookup | Forward pass consults owning-issue phase via a new walker helper; reverse pass unchanged | add helper `owning_issue_phase()` (or `wagon_has_entered_red()`) to `_acceptance_walker.py`; guard the forward-pass `violations.append` |
| coder | n/a — this is a tester-side validator refinement | n/a | none |
| coach | `.atdd/manifest.yaml` `sessions[].status` is the lifecycle phase source the State Store (#1168) imports | Same source, now also *read* (read-only) by the binding validator | none (read-only consumer; no schema change) |

### Existing Patterns

| Pattern | Example File | Convention |
|---------|--------------|------------|
| Substrate enforcement validator with `collect_violations(repo_root)` | `src/atdd/tester/validators/test_repo_validator_binding.py` | `tester.acceptance-violation.*` |
| Shared raw plan walker + phase/harness predicates | `src/atdd/tester/validators/_acceptance_walker.py` (`acceptance_phase`, `has_harness_type`, `iter_repo_acceptances`) | spec v12 §7.3 |
| Hermetic fixture tests driving `collect_violations(tmp_path)` | `src/atdd/tester/validators/tests/test_acceptance_violation_fixtures.py` | fixture-RED model |
| Anchored test header block (multi-`# Acceptance:`) | `src/atdd/tester/validators/tests/test_live_smoke_execution_fixtures.py` | `acceptance-test-headers.recipe.yaml` |
| Canonical phase order as data | `src/atdd/coach/conventions/phase_machine.convention.yaml` | `coach.phase-machine` |

### Conceptual Model

| Term | Definition | Example |
|------|------------|---------|
| owning issue | The GitHub/local issue whose `atdd` session authored an acceptance's WMBT | acceptance `acc:govern-lifecycle:E057-UNIT-001` is owned by issue #1242 |
| current phase | The owning issue's live lifecycle position, = `.atdd/manifest.yaml` `sessions[].status` | `PLANNED`, `RED`, `REFACTOR` |
| pre-test phase | A phase strictly before RED in `phase_machine` order — the window where acceptance tests are not yet authored | `INIT`, `PLANNED` |
| test-due | The point (RED onward) at which an acceptance's anchored test must exist | issue at `RED`+ |
| fail-closed | When ownership/phase can't be positively determined, **require** the test (today's behavior) — never silently exempt | unmapped wagon, malformed manifest |

### Before State

```
forward pass (per acceptance with harness.type, no anchored test):
    -> ALWAYS emit validator-binding-must-be-bidirectional   # phase-blind
```

### After State

```
forward pass (per acceptance with harness.type, no anchored test):
    owner_phase = owning_issue_phase(repo_root, acceptance)   # via .atdd/manifest.yaml sessions, keyed by wagon
    if owner_phase is a pre-test phase (INIT/PLANNED, per phase_machine order):
        -> EXEMPT (test not due yet)
    else:                                                     # RED+, COMPLETE, BLOCKED, unknown, unmapped
        -> emit validator-binding-must-be-bidirectional       # fail-closed: unchanged behavior
reverse pass: unchanged (phase-blind orphan-test detection)
```

---

## Rule Wiring

(No new convention rules. This issue refines the *enforcement timing* of the existing
`tester.acceptance-violation.validator-binding-must-be-bidirectional`; its rule_id, severity,
disposition, binding, and recipe are unchanged.)

| rule_id | severity | disposition | bind_to | fix_hint_ref |
|---------|----------|-------------|---------|--------------|
| _(none — existing rule refined, not added)_ | | | | |

---

## Phases

### Phase 1: Phase-aware forward pass

**Deliverables:**
- `owning_issue_phase()` (+ a `is_pre_test_phase()` / phase-rank comparison grounded in `phase_machine`) in `_acceptance_walker.py` — reads `.atdd/manifest.yaml` sessions, keys by wagon, fail-closed.
- Forward pass in `test_repo_validator_binding.py` guarded by the helper; reverse pass untouched.
- WMBT `E057` (5 acceptances) + feature `phase-aware-validator-binding` + anchored tests.

**Files:**

| File | Change |
|------|--------|
| `src/atdd/tester/validators/_acceptance_walker.py` | add `owning_issue_phase()` + phase-order comparison helper; export them |
| `src/atdd/tester/validators/test_repo_validator_binding.py` | forward pass: exempt acceptance when owning phase is pre-test (INIT/PLANNED) |
| `plan/govern_lifecycle/E057.yaml` | new WMBT, 5 acceptances |
| `plan/govern_lifecycle/features/phase_aware_validator_binding.yaml` | new feature descriptor |
| `plan/govern_lifecycle/_govern_lifecycle.yaml` | register feature URN |
| `src/atdd/tester/validators/tests/test_phase_aware_validator_binding.py` | anchored hermetic tests for E057 |
| `.atdd/manifest.yaml` | register session #1242 |

---

## Validation

### Gate Tests

| ID | Phase | Command | Expected | ATDD Validator | Status |
|----|-------|---------|----------|----------------|--------|
| GT-001 | design | `atdd validate planner --local --skip-api` | PASS | `src/atdd/planner/validators/` | TODO |
| GT-010 | design | `atdd validate tester --local --skip-api` | PASS | `src/atdd/tester/validators/` | TODO |
| GT-020 | design | `PYTHONPATH=src python -m pytest src/atdd/tester/validators/tests/test_phase_aware_validator_binding.py -q` | PASS | this issue's tests | TODO |
| GT-030 | design | `PYTHONPATH=src python -m pytest src/atdd/tester/validators/tests/test_acceptance_violation_fixtures.py -q` | PASS (no regression) | existing binding fixtures | TODO |
| GT-800 | completion | `atdd repo validate` | PASS | `src/atdd/coach/validators/test_urn_traceability.py` | TODO |
| GT-900 | completion | `atdd validate` | PASS | `src/atdd/` | TODO |

### Success Criteria

- [ ] **AC-1 (exempt pre-RED):** a harness acceptance with no anchored test whose owning wagon's issue(s) are all at INIT/PLANNED produces **zero** `validator-binding-must-be-bidirectional` violations.
- [ ] **AC-2 (RED+ still enforced):** the same acceptance, when the owning wagon has an issue at RED+ (or the issue itself is RED+), **still** produces the violation — invariant not weakened.
- [ ] **AC-3 (reverse pass unchanged):** an orphan test header naming a non-existent `acc:*` URN still fires, independent of any phase/manifest.
- [ ] **AC-4 (phase ordering):** `INIT` and `PLANNED` compare as pre-test (`< RED`); `RED/GREEN/SMOKE/REFACTOR/COMPLETE` and unknown/`BLOCKED` do not — order sourced from `phase_machine.convention.yaml`.
- [ ] **AC-5 (no regression / fail-closed):** with no `.atdd/manifest.yaml`, every existing binding fixture test and the real-repo `collect_violations()` (currently 0 violations) are unchanged.

---

## Decisions

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| 1 | What is "the phase at which the test is due"? | **RED.** Exempt iff owning issue is at INIT or PLANNED. | Tests are authored at the RED transition; before RED no test files exist. The acceptance's own `identity.phase` is the test's *target* phase (static, e.g. `GREEN`) — it is **not** the owning issue's live position and cannot answer "is the test due yet." |
| 2 | What is the authoritative source for an issue's current phase, and how do we avoid forking #1168? | Read `.atdd/manifest.yaml` `sessions[].status` (read-only) — the exact input the #1168 State Store imports (`atdd state import-manifest`). Centralize in one helper so the body can later swap to a State Store read API. | The State Store's SQLite DB is a *derived projection* that may be absent/stale in an arbitrary repo (e.g. hermetic fixtures); the manifest is always present and uses the **same** phase vocabulary as `phase_machine`. Manifest status values observed: `INIT/PLANNED/RED/GREEN/SMOKE/REFACTOR/COMPLETE/BLOCKED` — a perfect subset of `phase_machine`. |
| 3 | How does a repo-wide acceptance map to one owning issue? | Key by **wagon** (from the acceptance URN `acc:<wagon>:…` / its `plan/<wagon>/` dir), matched against `sessions[].wagon` (and `sessions[].train` for train-level acceptances). | `sessions[].file` is unusable (~2% populated, set by no command); WMBT YAML carries no `feature`/`issue` backref; so wagon is the only robust, always-present key. Documented limitation + future tightening in **Notes → Review Log, Pass 1**. |
| 4 | Wagon can host issues at different phases — how do we avoid weakening RED+? | **Fail-closed "max-phase":** exempt only if sessions for the wagon exist **and all** are pre-test (INIT/PLANNED). Any RED+ session in the wagon, an unmapped wagon, or a malformed manifest → **require** the test. | Guarantees we never stop enforcing for an established wagon; we only relax brand-new/all-early wagons — exactly the false-positive case. |
| 5 | Phase ordering source? | Read the linear order from `phase_machine.convention.yaml`; compare ranks; `BLOCKED`/`OBSOLETE`/unknown rank as not-pre-test (require). | One canonical phase order; no duplicated table (the duplicate state machine was removed in #888). |
| 6 | Release class? | **MINOR.** | Behavior refinement of an existing validator that only *relaxes* (at INIT/PLANNED); no breaking CLI/schema/convention change, no rule added or removed. |

---

## Activity Log

### Entry 1 (2026-06-29)

**Completed:**
- Issue created via `atdd issue phase-aware-validator-binding`.
- Grounded the bug: `test_repo_validator_binding.py` forward pass (~L122–147) emits unconditionally; real repo currently reports **0** binding violations (so this change is purely additive there).
- Resolved the phase-source mechanism (manifest `sessions[].status`, keyed by wagon, fail-closed) and the wagon/feature/train fit (govern-lifecycle / commons / 0001).
- 3-pass review (see Notes → Review Log).

**Next:**
- Plan feature + WMBT E057 + acceptances; write anchored RED tests; implement the GREEN phase-aware guard; validate full tester suite; push; `atdd pr 1242`; set PLANNED.

---

## Artifacts

### Created

- `plan/govern_lifecycle/E057.yaml` (WMBT, 5 acceptances)
- `plan/govern_lifecycle/features/phase_aware_validator_binding.yaml` (feature)
- `src/atdd/tester/validators/tests/test_phase_aware_validator_binding.py` (anchored tests)
- `docs/ISSUE-1242-PHASE-AWARE-BINDING.md` (this body)

### Modified

- `src/atdd/tester/validators/_acceptance_walker.py` (owning-issue-phase helper)
- `src/atdd/tester/validators/test_repo_validator_binding.py` (phase-aware forward pass)
- `plan/govern_lifecycle/_govern_lifecycle.yaml` (feature registration)
- `.atdd/manifest.yaml` (session #1242)

### Deleted

- (none)

---

## Release Gate

INTERIM (see #1172): bump the version manually. Branch prefix `feat/` + change class MINOR.

- [ ] Rebase on main: `git pull origin main --rebase`
- [ ] Bump version (MINOR): edit `pyproject.toml`, commit "Bump version to X.Y.Z"
- [ ] Merge PR → `publish.yml` tags + publishes from the version on main

**Change class: MINOR** — relaxes a validator at INIT/PLANNED without weakening RED+; non-breaking.

---

## Notes

The forward pass is the only behavior touched. The reverse pass, the rule node, the rule_id,
its severity/disposition, and every sibling acceptance-violation validator are untouched. The
helper is the single point that knows "current phase of the owning issue," so the eventual
#1168 State Store read-API migration is a one-function change.

### Review Log

**Pass 1 — systemic (does the mechanism read the right phase for every acceptance, including acceptances whose issue isn't in the manifest?)**
- The mechanism keys an acceptance to its owning issue by **wagon** and reads `sessions[].status`. Confirmed the phase vocabulary in the manifest is a subset of `phase_machine` (`INIT/PLANNED/RED/GREEN/SMOKE/REFACTOR/COMPLETE/BLOCKED`), so the comparison is well-defined.
- **Granularity limitation (surfaced & accepted):** `sessions[].file` is populated for ~2% of entries and by no command; WMBT YAML carries no `feature`/`issue` backref. So per-issue precision isn't derivable — wagon is the finest robust key. To avoid weakening RED+, the rule is **fail-closed "max-phase"**: exempt only when *all* sessions for the wagon are pre-test. Consequence: a new PLANNED issue that joins an **already-RED+ shared wagon** (e.g. `govern-lifecycle` itself) is **not** exempted — its operator still anchors tests at PLANNED. This is acceptable: it never produces a false *negative* (never stops enforcing), only retains a narrower false *positive* than today, and the clean case (new/all-early wagon) is fixed.
- **Acceptance whose owning issue isn't in the manifest:** fail-closed → the wagon has no matching session → **require** the test (today's behavior). One residual edge: an acceptance whose true owner is an *unlisted* RED+ issue but whose wagon contains *only* PLANNED sessions would be wrongly exempted. This requires an unregistered RED+ issue sharing a wagon with only-PLANNED issues — rare, and strictly less harmful than the status quo's forced `emergency`. Documented as **Edge E3** below; tightened automatically once #1168 indexes plan-file → issue.
- **#1168 coordination:** we read the State Store's *import source* (the manifest), not a forked store, using the shared phase vocabulary. *Changed by this pass:* added Decision #2's explicit "derived projection may be absent/stale → read the manifest, centralize for later swap" rationale, and the fail-closed semantics in Decision #4.

**Pass 2 — plan-fit (coordinates with #1168; doesn't collide with #1238/#1223 mid-RED on the current gate)**
- #1238 and #1223 are mid-RED and rely on the *present* gate: their acceptances already have anchored tests (they pushed under the current phase-blind rule). This change only *adds an exemption branch* for pre-RED issues; for any RED+ issue (including #1238/#1223 once they advance) the forward pass is byte-for-byte the same. Landing **after** they push is safe and does **not** retroactively touch their now-present tests (those still bind and still pass the reverse pass). *Changed by this pass:* added the explicit "land after #1238/#1223 push" note to Dependencies and this paragraph; confirmed no shared files (they touch enforce-binding-plan / schema-driven-issue-body, not `test_repo_validator_binding.py`).
- **Fit:** new feature under the existing `govern-lifecycle` wagon / `commons` theme / train `0001-self-compliance-validate`; no new theme invented; sits beside the other acceptance-violation substrate features. *Changed by this pass:* pinned the exact train_id and feature URN naming after reading `_govern_lifecycle.yaml` + `0001-self-compliance-validate.yaml`.

**Pass 3 — comprehensiveness (criteria measurable; edge cases)**
- All five success criteria are mechanically checkable by the E057 acceptances + anchored tests (each calls `collect_violations(tmp_path)` over a hermetic `plan/` + `.atdd/manifest.yaml`, or asserts the phase-order helper directly). *Changed by this pass:* split the original "exempt" criterion into AC-1/AC-2/AC-5 so "does not weaken" and "fail-closed/no-regression" are each independently asserted, and added AC-4 for the phase-order unit.
- **Edge cases enumerated & covered:**
  - **E1 — acceptance with no owning session / no manifest:** fail-closed → require (covered by AC-5 + existing fixtures, which carry no manifest and must stay green).
  - **E2 — issue at COMPLETE (or any RED+):** not pre-test → require (AC-2).
  - **E3 — malformed/unreadable manifest:** treated as "no sessions" → fail-closed require (helper swallows the YAML error like `_acceptance_walker._iter_acceptances_in_file` already does, logging at debug).
  - **E4 — train-level acceptance (`acc:<train_id>:…`):** match `sessions[].train`; if none, fail-closed require.
  - **E5 — BLOCKED/OBSOLETE owner:** ranked as not-pre-test → require (conservative; a blocked issue's tests may already be expected).

### Out-of-band verification notes

- Source-vs-installed: the pre-push bidirectional-binding gate runs the **installed** (phase-blind) validator, so #1242's own acceptances are anchored with real tests regardless of this fix — there is no chicken-and-egg. The phase-aware behavior is proven hermetically via the E057 fixtures, not via #1242's own push.
- Run source tests with `PYTHONPATH=src ~/.local/pipx/venvs/atdd/bin/python -m pytest …` (the installed CLI executes installed logic).
