# Coach v9 Runtime Layout

> **Status:** Frozen at C0 (issue #483). Every coach v9 track (J1, K1, L1, M1, N1, O1, P1) reads/writes against this contract; new files require an explicit follow-up issue.
>
> **Sibling contracts:**
> [`runtime-event.schema.json`](./runtime-event.schema.json) ·
> [`coach-decision.schema.json`](./coach-decision.schema.json) ·
> [`coach-judgment.schema.json`](./coach-judgment.schema.json) ·
> [`correction.schema.json`](./correction.schema.json) ·
> [`validator-result.schema.json`](./validator-result.schema.json) ·
> [`risk-score.schema.json`](./risk-score.schema.json) ·
> [`event-semantics.md`](./event-semantics.md) ·
> [`validator-invocation.md`](./validator-invocation.md)

This document specifies the directory and file structure under
`.atdd/runtime/`. For every file we name:

- **role** — what the file is for, in one sentence;
- **writer** — the single component allowed to write it;
- **reader** — the components that consume it;
- **appendability** — whether the file is **append-only** (one JSON
  document per line, never rewritten in place) or **rewritten** in full
  on every update;
- **serialization shape** — whether the file is a **JSON-line** stream
  (`*.jsonl`) or a **single-doc** JSON document (`*.json`).

Plain `*.log` files are byte streams, not JSON; we still record their
role/writer/reader and they are always append-only.

The directory tree is opaque to `git`: `.atdd/runtime/` is gitignored.
Anything under it is local to a coach run; nothing here is committed.

---

## Top-level tree

```
.atdd/runtime/
├── agents/<id>/
│   ├── heartbeat.json
│   ├── output.log
│   ├── events.jsonl
│   ├── corrections.jsonl
│   ├── questions.jsonl
│   ├── escalations.jsonl
│   ├── done.json
│   ├── context.json
│   ├── answers/<question-id>.json
│   └── reviews/<review-id>.json
├── coach/
│   ├── decisions.jsonl
│   └── judgments.jsonl
├── validations/<sha>/
│   ├── violations.jsonl
│   ├── risk-score.json
│   ├── suppressed.jsonl
│   └── stale-suppressions.jsonl
├── issue-reviews/<issue-N>/
│   └── aggregate.json
└── runs/<run-id>/
    └── manifest.json
```

The five top-level subtrees — `agents/<id>/`, `coach/`,
`validations/<sha>/`, `issue-reviews/<issue-N>/`, `runs/<run-id>/` —
are the C0-frozen partition of runtime state. Every other coach v9
artifact MUST live under one of them.

### Path index (full paths)

Every file documented below, listed in full-path form so consumers can
grep this document for an exact match:

- `.atdd/runtime/agents/<id>/heartbeat.json`
- `.atdd/runtime/agents/<id>/output.log`
- `.atdd/runtime/agents/<id>/events.jsonl`
- `.atdd/runtime/agents/<id>/corrections.jsonl`
- `.atdd/runtime/agents/<id>/questions.jsonl`
- `.atdd/runtime/agents/<id>/escalations.jsonl`
- `.atdd/runtime/agents/<id>/done.json`
- `.atdd/runtime/agents/<id>/context.json`
- `.atdd/runtime/agents/<id>/answers/<question-id>.json`
- `.atdd/runtime/agents/<id>/reviews/<review-id>.json`
- `.atdd/runtime/coach/decisions.jsonl`
- `.atdd/runtime/coach/judgments.jsonl`
- `.atdd/runtime/validations/<sha>/violations.jsonl`
- `.atdd/runtime/validations/<sha>/risk-score.json`
- `.atdd/runtime/validations/<sha>/suppressed.jsonl`
- `.atdd/runtime/validations/<sha>/stale-suppressions.jsonl`
- `.atdd/runtime/issue-reviews/<issue-N>/aggregate.json`
- `.atdd/runtime/runs/<run-id>/manifest.json`

---

## `agents/<id>/` — per-agent runtime state

Each spawned agent owns a directory keyed by its agent id (a slug like
`agent-J3-coach-state-machine` or a UUID — coach picks). The watcher
(#J5) writes; observer (#L1) and review reporters (#N2/#O2) read.

### `agents/<id>/heartbeat.json`

| facet | value |
|-------|-------|
| role | Liveness signal: last-known PID, wall-clock, and free-form status payload for one agent. Coach uses it to detect process_silence. |
| writer | Runtime watcher (#J5) |
| reader | Runtime watcher (silence detection); review reporters; the observer |
| appendability | **rewritten** in place — most recent state replaces the previous |
| serialization shape | **single-doc** JSON |
| schema | (no committed schema — one-key-only `{pid, observed_at, status}`; if grown beyond that, file a follow-up to add one) |

### `agents/<id>/output.log`

| facet | value |
|-------|-------|
| role | Captured stdout/stderr stream of the agent process. Used for postmortem and for observer pattern matching. |
| writer | Runtime watcher (#J5) — tee'd from the agent's pipe |
| reader | Observer (#L1); human review |
| appendability | **append-only** byte stream |
| serialization shape | not JSON — line-buffered text log |

### `agents/<id>/events.jsonl`

| facet | value |
|-------|-------|
| role | Per-agent runtime event stream — one event document per line. The 12 event types are frozen at C0. |
| writer | Runtime watcher (#J5) |
| reader | Observer (#L1); git watcher (#M1); review reporters; the observer |
| appendability | **append-only** — never rewritten in place |
| serialization shape | **JSON-line** stream |
| schema | [`runtime-event.schema.json`](./runtime-event.schema.json) — temporal contracts in [`event-semantics.md`](./event-semantics.md) |

### `agents/<id>/corrections.jsonl`

| facet | value |
|-------|-------|
| role | Observer-issued corrections that the watcher injected into the agent. One record per correction. |
| writer | Runtime watcher (#J5) — after observer (#L1) emits |
| reader | Observer (re-evaluation); review reporters; audit |
| appendability | **append-only** |
| serialization shape | **JSON-line** stream |
| schema | [`correction.schema.json`](./correction.schema.json) |

### `agents/<id>/questions.jsonl`

| facet | value |
|-------|-------|
| role | Structured agent → coach questions emitted via `atdd agent ask`. One record per question with `question_id`, `type` (choice/text/approval/confirmation), `question`, and `timestamp`. |
| writer | Persona agent via `atdd agent ask` (J2 — #497) |
| reader | Coach state machine (#J3) — answers via `answers/<question-id>.json`; review reporters |
| appendability | **append-only** |
| serialization shape | **JSON-line** stream |
| schema | (no committed schema yet — frozen alongside the coach-side answer writer in #J3) |

### `agents/<id>/escalations.jsonl`

| facet | value |
|-------|-------|
| role | Agent-emitted escalations via `atdd agent escalate`. One record per escalation with `reason`, `severity` (info/warn/block), and `timestamp`. |
| writer | Persona agent via `atdd agent escalate` (J2 — #497) |
| reader | Observer (#L1); coach state machine (#J3) for severity=block routing; review reporters |
| appendability | **append-only** |
| serialization shape | **JSON-line** stream |
| schema | (no committed schema yet — frozen alongside the observer-side consumer in #L1) |

### `agents/<id>/done.json`

| facet | value |
|-------|-------|
| role | Final-summary record signalling persona completion via `atdd agent done`. |
| writer | Persona agent via `atdd agent done` (J2 — #497) |
| reader | Coach state machine (#J3) — drives the per-issue REFACTOR→COMPLETE transition; review reporters |
| appendability | **rewritten** in place — only the most recent done-signal is meaningful per agent |
| serialization shape | **single-doc** JSON |
| schema | (no committed schema yet — frozen alongside the coach-side consumer in #J3) |

### `agents/<id>/context.json`

| facet | value |
|-------|-------|
| role | Spawn-time bundle the spawner writes for the agent: current `phase`, `wmbt_urn`, `issue`, plus any per-LLM convention pointers. Read-only from the agent's perspective. |
| writer | Spawner / spawn-harness (#K4) at agent-spawn time |
| reader | Persona agent via `atdd agent context` (J2 — #497) |
| appendability | **rewritten** by the spawner only — agent never writes |
| serialization shape | **single-doc** JSON |
| schema | (no committed schema yet — frozen alongside the spawn-harness in #K4) |

### `agents/<id>/answers/<question-id>.json`

| facet | value |
|-------|-------|
| role | Coach's answer to a specific `atdd agent ask` question, keyed by `question_id`. The round-trip path is the only contract — no shared mutable state between agent and coach. |
| writer | Coach state machine (#J3) — one file per answered question |
| reader | Persona agent via `atdd.coach.commands.agent.read_answer()` (J2 — #497) |
| appendability | **rewritten** if coach revises an answer (rare); each question_id maps to at most one file |
| serialization shape | **single-doc** JSON |
| schema | (no committed schema yet — frozen alongside the coach-side answer writer in #J3) |

### `agents/<id>/reviews/<review-id>.json`

| facet | value |
|-------|-------|
| role | Reviewer-only output channel (spec §6.3 hard rule): one record per review with `review_id`, `target_commit`, the report body, and `timestamp`. The full reviewer persona spawn (no-write adapter, etc.) is owned by #N1/#N5; J2 ships only the CLI surface. |
| writer | Reviewer persona via `atdd agent review` (J2 — #497) |
| reader | Review-report writer (#N2); reviewer-agents (#O2); audit |
| appendability | **append-only** under the directory — one new file per review_id; existing files are never rewritten |
| serialization shape | **single-doc** JSON (one file per review) |
| schema | (no committed schema yet — frozen alongside the reviewer persona in #N1/#N5) |

---

## `coach/` — process-wide coach state

Coach state that is not bound to any single agent. Writer is always the
coach state machine (#J3); readers are reporters and the audit pipeline.

### `coach/decisions.jsonl`

| facet | value |
|-------|-------|
| role | Append-only ledger of every decision the coach took (state transitions, configuration choices, escalations). Spec §4.5 / §C0. |
| writer | Coach state machine (#J3) |
| reader | Review reporters (#N2/#O2); audit tooling |
| appendability | **append-only** |
| serialization shape | **JSON-line** stream |
| schema | [`coach-decision.schema.json`](./coach-decision.schema.json) |

### `coach/judgments.jsonl`

| facet | value |
|-------|-------|
| role | Append-only ledger of every LLM-judgment call the coach made (one of the six call sites per spec §6.9). Acts as the durable cache index. |
| writer | Coach state machine (#J3) via the judge wagon |
| reader | Cache lookup; review reporters; audit |
| appendability | **append-only** |
| serialization shape | **JSON-line** stream |
| schema | [`coach-judgment.schema.json`](./coach-judgment.schema.json) |

---

## `validations/<sha>/` — per-commit validator artifacts

One subdirectory per commit SHA the coach has validated against. The
SHA-anchored layout makes risk scores reproducible and lets the
review-reporter aggregate per-commit history without scanning logs.

### `validations/<sha>/violations.jsonl`

| facet | value |
|-------|-------|
| role | Every structured `Violation` raised at this SHA, serialized through the C0 contract. Spec §6.4 / §7.5. |
| writer | Pytest violation-collector plugin (#M2) |
| reader | Review-report writer (#N2); reviewer-agents (#O2); risk-scorer |
| appendability | **append-only** during one validation run; the *file* is rewritten only when the SHA changes (a new SHA gets a new directory). |
| serialization shape | **JSON-line** stream |
| schema | [`validator-result.schema.json`](./validator-result.schema.json) |

### `validations/<sha>/risk-score.json`

| facet | value |
|-------|-------|
| role | Aggregate risk score for the SHA — `sum`, `by_severity`, `by_archetype` (incl. `repo`), `by_disposition`, `stale_suppressions`. Spec §6.8. |
| writer | Risk-scorer (#M3) — runs after the violation-collector flushes |
| reader | PR-routing logic; auto-phase gate; review reporters |
| appendability | **rewritten** on every phase exit at this SHA |
| serialization shape | **single-doc** JSON |
| schema | [`risk-score.schema.json`](./risk-score.schema.json) |

### `validations/<sha>/suppressed.jsonl`

| facet | value |
|-------|-------|
| role | Violations that were absorbed by an inline `# atdd:suppress(...)` marker. Useful for "what is suppression masking?" review questions. |
| writer | Pytest violation-collector plugin (#M2) — same writer as `violations.jsonl` but routed through the disposition gate |
| reader | Review-report writer; suppression audit |
| appendability | **append-only** for the SHA |
| serialization shape | **JSON-line** stream |
| schema | [`validator-result.schema.json`](./validator-result.schema.json) (records carry a non-null `suppression_marker`) |

### `validations/<sha>/stale-suppressions.jsonl`

| facet | value |
|-------|-------|
| role | Suppression markers whose `UNTIL=<date>` is in the past. The coach gate fails on a non-zero count of these. |
| writer | Suppression scanner (substrate v12) — invoked by coach at validate time |
| reader | Coach gate; review reporters |
| appendability | **append-only** for the SHA |
| serialization shape | **JSON-line** stream |
| schema | (no committed schema yet — substrate's scanner shape is the source; if frozen later, file a follow-up to add one) |

---

## `issue-reviews/<issue-N>/` — per-parent-issue aggregate

Spec §6.10. One subdirectory per ATDD parent issue, holding the rolled-up
review payload that the reporter writes to GitHub.

### `issue-reviews/<issue-N>/aggregate.json`

| facet | value |
|-------|-------|
| role | Cross-SHA roll-up: latest risk score, list of open violations, link to last review-complete event. Drives the parent-issue review comment. |
| writer | Review-report writer (#N2) |
| reader | Reviewer-agents (#O2); auto-phase gate |
| appendability | **rewritten** every time the writer recomputes the aggregate |
| serialization shape | **single-doc** JSON |
| schema | (no committed schema yet — frozen in a downstream issue alongside the writer that will produce it) |

---

## `runs/<run-id>/` — coach-run scoped manifest

One subdirectory per coach orchestration run (a `coach_run_id`). Holds
the manifest that ties together the agents spawned and the SHAs
validated within this run, so postmortem can be reconstructed without
walking the union of `agents/`, `coach/`, and `validations/`.

### `runs/<run-id>/manifest.json`

| facet | value |
|-------|-------|
| role | Run-scoped index: list of agent ids, list of validation SHAs, start/end timestamps, exit status. |
| writer | Coach state machine (#J3) — finalized at run end |
| reader | Postmortem tooling; review reporters |
| appendability | **rewritten** at run-end (and incrementally during the run if the implementer chooses) |
| serialization shape | **single-doc** JSON |
| schema | (no committed schema yet — frozen alongside the run-orchestrator that produces it) |

---

## Conventions across the layout

1. **Append-only files never seek-and-truncate.** A coach instance may
   crash; the JSONL writer MUST be safe under crash-recover by reopening
   in append mode.
2. **Single-doc files are written atomically.** Implementers MUST write
   to `<path>.tmp` and `os.rename` into place to avoid partial reads.
3. **Schemas freeze shape; semantics live in sibling docs.** Temporal
   contracts (idempotency, ordering, replay) for runtime events live in
   [`event-semantics.md`](./event-semantics.md). The validator
   subprocess contract lives in
   [`validator-invocation.md`](./validator-invocation.md).
4. **Cross-references use relative paths.** The schemas referenced
   above (`runtime-event.schema.json`, `coach-decision.schema.json`,
   `coach-judgment.schema.json`, `correction.schema.json`,
   `validator-result.schema.json`, `risk-score.schema.json`) are
   sibling files in `src/atdd/coach/schemas/` and are linked
   accordingly.
