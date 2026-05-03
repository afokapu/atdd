# Worker Context Window Management SPEC

`SPEC-COACH-WORKER-0001..0004`

Long-running ATDD waves can drive a single agent's context window past the
effective cap, at which point the worker either thrashes on its own
deliberation or becomes unrecoverable. This SPEC defines the minimal
substrate — checkpoint file + token alert + re-brief renderer — that lets a
worker self-regulate without orchestrator intervention.

Source: issue #378.

---

## SPEC-COACH-WORKER-0001 — Checkpoint contract

After every phase transition (`RED → GREEN`, `GREEN → SMOKE`, etc.) the
worker MUST be able to persist its state to:

```
.atdd/worker-state-{issue}.json
```

The path is gitignored (per `.gitignore::.atdd/worker-state-*.json`) — the
file is a per-session artifact, not history.

Schema: `src/atdd/coach/schemas/worker-state.schema.json`. Required fields:

| Field             | Description                                                            |
|-------------------|------------------------------------------------------------------------|
| `issue`           | GitHub issue number (anchors the worker to its assignment)             |
| `phase`           | One of `INIT|PLANNED|RED|GREEN|SMOKE|REFACTOR|COMPLETE|BLOCKED`        |
| `summary`         | ≤500 chars; truncated by the writer                                    |
| `open_files`      | Files the worker was actively editing                                  |
| `checkpointed_at` | ISO-8601 UTC timestamp                                                 |

Optional: `branch`, `last_commit`, `ttl_seconds` (advisory; default 86400s).

Writer: `atdd checkpoint <N> --phase X --summary "..." --open-files a.py,b.py`.
Implementation: `src/atdd/coach/commands/checkpoint.py::write_worker_checkpoint`.
Atomic: payload is staged to `.tmp` and renamed.

---

## SPEC-COACH-WORKER-0002 — Token-count alert

`atdd babysit` reads each workspace's token count and emits an
`escalate` decision (and a `token_threshold` JSONL event) when the count
crosses the configured threshold.

| Setting     | Value                                                                |
|-------------|----------------------------------------------------------------------|
| Default     | `400000` (≈200k headroom under the typical 600k effective cap)       |
| Override    | `babysit.token_alert_threshold` in `.atdd/config.yaml`               |
| CLI flag    | `atdd babysit --token-alert-threshold N`                             |
| Source      | `claude --print-context-status` (Decision 6)                         |
| Fallback    | `None` → no alert (rendered as `—` in dashboards)                    |

Implementation: `src/atdd/coach/commands/babysit.py::check_token_threshold`,
`read_token_count`.

---

## SPEC-COACH-WORKER-0003 — `/compact` discipline (advisory)

Workers SHOULD run `/compact` after each phase transition. This is
**advisory in v1**: not enforced by a validator.

If a worker exceeds the alert threshold without a prior `/compact`,
promote this rule to a validator-enforced check (requires per-session
telemetry that is not yet wired).

---

## SPEC-COACH-WORKER-0004 — Re-brief from checkpoint

`atdd session-template <N> --from-checkpoint` regenerates a launch prompt
that includes the original spec **and** an inline `## Resumed from
checkpoint` block sourced from `.atdd/worker-state-<N>.json`. The block
contains:

- The phase, last commit, and `checkpointed_at` timestamp
- The summary recorded at the last checkpoint
- The open-files list

When no checkpoint file exists, the command falls back to the default
launch-script render — there is no error path that prevents an orchestrator
from using `--from-checkpoint` unconditionally.

Implementation: `src/atdd/coach/commands/session_template.py::render_with_checkpoint`.

---

## Lifecycle

```
[RED tests done]
    └─► atdd issue 378 --status RED
    └─► atdd checkpoint 378 --phase RED --summary "..." --open-files ...
    └─► /compact

[token alert fires at 400k+]
    └─► /compact
    └─► (optional) /clear
    └─► atdd session-template 378 --from-checkpoint
    └─► resume work
```

---

## Out of scope

- **Auto-`/clear` injection.** Workers self-regulate; the SPEC supplies tooling, not triggers.
- **Cross-session checkpoint replay.** Resuming a worker from a 24h-old checkpoint is out of scope for v1.
- **Multi-agent context sharing.** One checkpoint per issue; no cross-worker reads.
- **Token-cost reporting / billing.** Tracked separately; see #326 if it lands.
