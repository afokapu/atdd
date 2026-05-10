# Babysit ↔ Observer Differences-Allowed Oracle

Authoritative oracle for the parity assertions in
`test_babysit_observer_parity.py`. Documents which differences between
`atdd babysit` and `atdd observer` are intentional and do not constitute
parity failures.

## Allowed Differences

### 1. corrections.jsonl additions

Observer's rule evaluation may produce additional correction records that
babysit never wrote (e.g., token-threshold corrections, richer metadata
fields like `issued_at`, `validator_id`). These are durability metadata
added by the observer framework, not behavioral differences.

### 2. Dashboard-format minor whitespace

Dashboard rendering is shared (`_render_dashboard` is re-exported from
observer by babysit). If a future refactor introduces trailing whitespace
differences, those are not parity failures. The parity test normalizes
trailing whitespace before comparison.

### 3. Internal state representation

Babysit polls a multiplexer backend (`WorkspaceState`, `read_screen`).
Observer reads from `.atdd/runtime/agents/<id>/` filesystem paths
(`output.log`, `heartbeat.json`, `context.json`). The internal state
sources differ, but the classifier logic is shared (`classify_prompt`,
`detect_violation`, `correct_naming_drift`, `correct_layout_drift`).
Observable outputs (approve/escalate decisions, dashboard rows) must be
equivalent.

### 4. Naming-drift first-call semantics

Babysit's `correct_naming_drift` issues `backend.rename()` unconditionally
on the first call for a ref (no current-name check — it relies on the
`applied_cache` to skip already-applied renames within a single run). The
observer's predicate checks `is_canonical_name()` before firing. Both
paths converge to the same observable outcome (canonical name applied) —
the difference is whether a redundant rename call is issued.

### 5. Aggregate-approve I/O mechanism

Babysit's `aggregate_approve` reads screens from a multiplexer backend
(`backend.read_screen`) and sends approvals via `backend.send()`.
Observer's `cmd_aggregate_approve` reads from `output.log` files and
writes approval signals to `cli-return.jsonl`. Both use the same shared
classifiers (`classify_prompt`, `detect_violation`). The I/O mechanism
differs, but the approve/escalate decisions must be equivalent.

### 6. Log event format

Babysit writes to `orchestration-log.jsonl` with `event`-keyed records.
Observer writes to `corrections.jsonl` with correction-schema-validated
records. The log formats differ, but the underlying decisions are the
same.

## Parity Assertions

The test suite asserts equivalence on:

1. **Token alert**: both fire at the same threshold for the same token count.
2. **Bash auto-approve**: both agree on approve/escalate for the same screen.
3. **Naming drift**: both detect and correct the same drift (modulo first-call semantics).
4. **Layout drift**: both fire when the surface-count band changes.
5. **Smoke skip**: both flag GREEN→REFACTOR without SMOKE.
6. **Dashboard**: identical rendered output for the same input rows.
7. **Aggregate-approve**: both approve/escalate the same set of surfaces.

## Gating Contract

Per spec §11.3 and issue #P6: CI failure on this suite blocks babysit
decommissioning. The suite runs on every PR touching
`src/atdd/coach/commands/babysit.py` or `src/atdd/coach/commands/observer.py`
or `src/atdd/coach/observer_rules/`.
