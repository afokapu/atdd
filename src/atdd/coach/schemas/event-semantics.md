# Coach v9 Event Semantics

> **Status:** Frozen at C0 (issue #483).
>
> **Sibling contracts:**
> [`runtime-event.schema.json`](./runtime-event.schema.json) ·
> [`runtime-layout.md`](./runtime-layout.md) ·
> [`validator-invocation.md`](./validator-invocation.md)

[`runtime-event.schema.json`](./runtime-event.schema.json) freezes the
**shape** of every runtime event. This document freezes the
**semantics**: who emits each event, on what state change, what the
idempotency contract is, what ordering guarantees consumers can rely
on, and how the event behaves under `coach --resume`.

The 12 event types below are the closed set frozen at C0. They MUST
match the `event_type` enum in
[`runtime-event.schema.json`](./runtime-event.schema.json) one-for-one;
adding a new type requires an explicit follow-up issue.

---

## Glossary

- **At-least-once** — the producer guarantees the event will be
  written ≥1 times. Consumers MUST dedupe on the natural key.
- **Exactly-once** — the producer guarantees the event is written
  exactly once across crash and resume. Consumers do not need to
  dedupe.
- **Per-agent total order** — events for one `agent_id` are appended
  to that agent's `events.jsonl` in monotonic timestamp order; a
  consumer reading one agent's stream sees a total order.
- **Cross-agent partial order** — there is no synchronization clock
  across agents; a consumer joining two agents' streams MUST treat
  them as concurrent.
- **None** — no ordering guarantee; a consumer must look at the event
  payload to reconstruct order.
- **Replay re-fires** — on `coach --resume`, the event is emitted
  again from the durable state.
- **Replay suppressed** — on `coach --resume`, the event is not
  re-emitted; consumers see only the post-resume stream.
- **Replay cached** — on `coach --resume`, the producer reads its
  prior emission from the durable ledger and republishes it as a
  cached copy.

---

## `agent_spawned`

- **Producer.** Coach state machine (#J3), at the moment the agent
  subprocess has been launched and its `agents/<id>/heartbeat.json`
  has been first-written.
- **Triggering condition.** A `coach orchestrate` decision committed
  to spawn a new agent and the spawn syscall returned a PID. The
  event MUST NOT be emitted before the heartbeat file is on disk
  (consumers assume the agent directory exists when they see the
  event).
- **Idempotency.** **Exactly-once** per `agent_id` per coach run.
  Spawn is gated by the coach's run-scoped agent registry; a re-spawn
  produces a new `agent_id`, not a second `agent_spawned` for the
  old one.
- **Ordering.** Per-agent total order — trivially, since this is the
  first event in the agent's stream.
- **Replay.** **Replay cached** — `coach --resume` reads the prior
  event from `agents/<id>/events.jsonl` and republishes it; consumers
  do not see a fresh spawn.

## `heartbeat`

- **Producer.** Runtime watcher (#J5), on a periodic timer scoped to
  one agent.
- **Triggering condition.** The watcher's heartbeat tick fires AND
  the agent process is still alive (PID exists, no zombie). Each
  tick rewrites `heartbeat.json` and appends one event.
- **Idempotency.** **At-least-once.** A watcher restart can re-emit
  the most recent heartbeat. Consumers MUST dedupe on
  `(agent_id, payload.observed_at)` if exact-count matters.
- **Ordering.** Per-agent total order on the agent's stream.
- **Replay.** **Replay suppressed.** Heartbeats are not replayed on
  resume — they describe transient liveness, and a stale
  pre-resume heartbeat would be actively misleading.

## `commit_observed`

- **Producer.** Git watcher (#M1).
- **Triggering condition.** A new commit appears on the worktree's
  HEAD (detected by the git watcher polling `git rev-parse HEAD`
  against its last-seen value). The event payload carries the new
  SHA, the parent SHA, and the author.
- **Idempotency.** **At-least-once.** A watcher crash mid-emit can
  republish the same SHA; consumers MUST dedupe on `payload.sha`.
- **Ordering.** Per-agent total order on the worktree's git watcher
  stream; cross-agent partial order otherwise.
- **Replay.** **Replay cached** — on resume the watcher reconstructs
  its observed-SHA history from the prior `events.jsonl` and
  republishes the cached entries.

## `event_emitted`

- **Producer.** Coach state machine (#J3) — the meta-event the coach
  uses to record that *itself* fired any of the other 11 event types.
- **Triggering condition.** Any other event type was just appended.
  This is the audit-loop event, used to reconstruct what the coach
  emitted across all streams without scanning every agent.
- **Idempotency.** **At-least-once.** Pairs with the underlying
  event; consumers MUST dedupe on
  `(payload.original_event_id, payload.original_event_type)`.
- **Ordering.** None across the audit stream — events are inserted in
  the order the coach ratified each underlying event, but two
  underlying emissions can interleave.
- **Replay.** **Replay cached** — the audit stream is reconstructed
  from the union of underlying agent streams on resume.

## `escalation_emitted`

- **Producer.** Coach state machine (#J3), called by the judge wagon
  when the `escalation` judgment surface returns a non-null
  escalation target.
- **Triggering condition.** A `coach-judgment` record with
  `call_site: "escalation"` returned a non-null `response.target`.
  The event payload carries the target and the issue / agent context.
- **Idempotency.** **Exactly-once** per `(judgment_id)`. The judge
  wagon is the gating side; re-asking the same hashable inputs hits
  the cache and does not re-fire.
- **Ordering.** Cross-agent partial order — escalations across
  different agents have no synchronization.
- **Replay.** **Replay suppressed.** Escalations are external
  side-effects (notifications, human pages); they are not
  re-emitted on resume to avoid double-paging.

## `pr_opened`

- **Producer.** Coach state machine (#J3), after `atdd pr <N>`
  reports the PR was created.
- **Triggering condition.** A successful `atdd pr <N>` invocation
  returned a PR number. The event payload carries
  `{pr_number, base, head, sha}`.
- **Idempotency.** **Exactly-once** per `pr_number`. The coach
  records the PR number in its run manifest and refuses to re-emit
  for a known PR.
- **Ordering.** Cross-agent partial order — PRs from sibling agents
  carry no synchronization.
- **Replay.** **Replay cached** — on resume the coach reads the
  prior PR number from the run manifest and republishes the event.

## `pr_closed`

- **Producer.** Git watcher (#M1) for self-closed PRs; coach state
  machine (#J3) for coach-driven closures (merge or abort).
- **Triggering condition.** GitHub webhook or polled state shows the
  PR transitioned out of `open` (to `merged`, `closed`, or
  `auto-merge`). Payload includes the terminal state and the SHA.
- **Idempotency.** **At-least-once.** Polling can observe the
  transition twice if the webhook also fires; consumers MUST dedupe
  on `(pr_number, payload.terminal_state)`.
- **Ordering.** Cross-agent partial order.
- **Replay.** **Replay cached** for already-closed PRs; **replay
  suppressed** for PRs that were open at the resume point (those
  re-enter the live observation path).

## `validation_pending`

- **Producer.** Coach state machine (#J3) at the moment a phase
  transition starts and validators are about to be invoked.
- **Triggering condition.** A phase transition (e.g. RED → GREEN)
  has been ratified and the coach is about to spawn the validator
  subprocess (per [`validator-invocation.md`](./validator-invocation.md)).
- **Idempotency.** **Exactly-once** per `(coach_run_id, phase, sha)`
  — the coach gate guards against duplicate invocations on the same
  state.
- **Ordering.** Per-agent total order on the coach stream.
- **Replay.** **Replay suppressed.** A pending validation that was
  in flight at resume is not re-marked pending; the coach either
  re-runs the validation (and emits a fresh `validation_pending`)
  or treats the previous outcome as authoritative — never both.

## `validation_complete`

- **Producer.** Coach state machine (#J3), after the validator
  subprocess exited and the violation-collector plugin flushed its
  records to `validations/<sha>/violations.jsonl`.
- **Triggering condition.** The validator subprocess exited (with
  any status — see retry-policy in
  [`validator-invocation.md`](./validator-invocation.md) §4) AND the
  risk-scorer (#M3) finished writing `risk-score.json`.
- **Idempotency.** **Exactly-once** per `(coach_run_id, phase, sha)`.
  This is the durable signal the auto-phase gate consumes; duplicate
  emission would corrupt the gate's bookkeeping.
- **Ordering.** Per-agent total order on the coach stream; pairs
  monotonically with the matching `validation_pending`.
- **Replay.** **Replay cached** — on resume the coach reads the
  prior outcome from `validations/<sha>/risk-score.json` and
  republishes the cached `validation_complete`.

## `review_complete`

- **Producer.** Review-report writer (#N2) once the
  `issue-reviews/<issue-N>/aggregate.json` write finishes.
- **Triggering condition.** A reviewer-agent (#O2) finished
  consuming the latest `validation_complete` and the writer wrote
  the aggregated review payload.
- **Idempotency.** **At-least-once.** A writer crash mid-flush can
  republish; consumers MUST dedupe on
  `(payload.issue_number, payload.aggregate_sha)`.
- **Ordering.** Cross-agent partial order — reviews of different
  parent issues carry no synchronization.
- **Replay.** **Replay cached** — on resume the writer reads the
  prior `aggregate.json` and republishes the event.

## `correction_emitted`

- **Producer.** Observer (#L1) — the watcher's `corrections.jsonl`
  append of one [`correction.schema.json`](./correction.schema.json)
  record always pairs with this event.
- **Triggering condition.** Observer matched an agent-output rule and
  produced a correction record. The event payload carries the
  `(agent_id, rule_id, injection_method)` triple.
- **Idempotency.** **At-least-once** per natural key
  `(agent_id, rule_id, payload.detected_at)`. The observer's pattern
  match can re-fire on a second window; consumers MUST dedupe.
- **Ordering.** Per-agent total order.
- **Replay.** **Replay suppressed.** Corrections are external
  side-effects (they were already injected into the live agent);
  re-firing on resume would double-inject and confuse the agent.

## `process_silence`

- **Producer.** Runtime watcher (#J5), on the silence-detector tick.
- **Triggering condition.** No new bytes on the agent's
  `output.log`, no new commit observed, AND no `heartbeat` event for
  longer than the configured silence window. The event payload
  carries `silent_for_seconds`.
- **Idempotency.** **At-least-once.** A silence-detector restart
  can re-fire if the silence persists; consumers MUST dedupe on
  `(agent_id, payload.silence_window_started_at)`.
- **Ordering.** Per-agent total order.
- **Replay.** **Replay suppressed.** Silence is a transient liveness
  state; the post-resume detector starts fresh from the resume point
  and emits a new `process_silence` only if the silence persists.
