# Interlocking runtime boundary (#1251)

Runtime route-control contract for train interlockings. Parent: #1246.
Companion to the #1248 planner artifact API (`src/atdd/planner/interlocking/`)
and the #1249 planner validators. Implementation lives in
`src/atdd/runtime/interlocking/`.

## Call model

```text
HTTP/API/action layer  -> action + inputs
Station Master         -> resolve_journey(JOURNEY_MAP, action)
  direct:        DirectTrainTarget(train_id)        -> TrainRunner.execute(train_id, ...)
  interlocking:  InterlockingTarget(id, path)       -> InterlockingRunner(path, train_executor=TrainRunner)
                                                          .execute(action, inputs, state, timing, capture_trace)
InterlockingRunner.resolve_train -> exactly one InterlockingResolution
InterlockingRunner.execute       -> delegates selected train_id to TrainRunner.execute(...)
```

Direct `action -> train_id` routing remains valid. Interlocking routing is purely
additive: the Station Master `JOURNEY_MAP` accepts both a `train_id` string and an
`{interlocking_id, path}` mapping.

## Resolution contract (`resolve_train`)

Reuses the #1248 safe API only — `load_interlocking`, `validate_interlocking`,
`evaluate_interlocking_route`. Fails closed (`InterlockingResolutionError`) on:

- an unsound interlocking (any semantic violation),
- an unknown/unexposed entrypoint action,
- no matching route,
- multiple matching routes with no deterministic tie-breaker,
- a selected route whose `category_digit` disagrees with its `train_id` digit,
- a selected route whose target train file does not exist.

Returns a structured `InterlockingResolution` (not a bare string):
`interlocking_id, route_id, train_id, train_path, category, category_digit,
guard_id, resolution_strategy, reason`.

## Forbidden boundaries (enforced by contract tests + atdd-extensions #25/#26/#27)

The InterlockingRunner MUST NOT: execute a wagon step, mutate Cargo, choose the
next step inside a train, bypass or duplicate TrainRunner's execution loop, or use
raw Python `eval` for guards. Guards are evaluated through the #1248 declarative
grammar, which has no path to `eval`/`exec`.

## Trace

When an interlocking route is used, the runtime trace carries (via
`InterlockingResolution.as_trace()`, handed to the executor as `interlocking_trace`):
`interlocking_id, route_id, selected_train_id, route_category,
route_category_digit, guard_id, resolution_strategy, resolution_reason`.
TrainRunner remains responsible for step-level execution trace.

## Route-boundary transitions — DEFERRED

The issue permits implementing route-boundary transitions (inspecting a completed
`TrainResult` at an explicitly declared boundary, e.g. a `transitions:` block with
`from_route` / `on_result_guard` / `next_interlocking_id` / `next_action`) OR
explicitly deferring them.

They are **deferred** for #1251, with rationale:

1. Transitions require a completed `TrainResult` to inspect at a declared
   boundary. The production `TrainResult` shape (artifacts/trace surfaced to the
   route layer) is owned by the consuming runtime's TrainRunner, whose concrete
   `execute(...) -> TrainResult` is the subject of atdd-extensions #26 (production
   coverage) and #27 (trace-to-declaration binding), not of this core spec.
2. Landing a transition engine now would require this core layer to assume a
   `TrainResult` contract that the issue places out of scope ("Replacing
   TrainRunner", "Implicit TrainResult-driven chaining" are out of scope; chaining
   is forbidden unless declared at a boundary).

The deferral keeps #1251 to the single-route resolve+delegate boundary it
specifies. When transitions are taken up, they bind on top of
`InterlockingResolution` + the executor's `TrainResult` and reuse the same #1248
declarative guard grammar against the result facts at a declared boundary — no new
runtime assumptions are introduced by deferring.
