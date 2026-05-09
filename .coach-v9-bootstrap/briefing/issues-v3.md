# ATDD Coach v9 — Implementation Issues

> **Purpose**: ready-to-file GitHub issues for the coach implementation per `atdd-coach-spec-v9.md`.
> **Format**: each issue is one markdown block; copy into `gh issue create --title "..." --body-file -` or paste into the GitHub web UI.
> **Companion**: `atdd-coach-spec-v9.md` (the spec); `atdd-repo-substrate-spec-v12.md` (substrate, already shipped).
> **Changes from v2**: Extended #C0 with `event-semantics.md` artifact (temporal contracts for the 12 event types). Strengthened #J5 acceptance criteria with concurrency tests (watcher reattachment, duplicate suppression, append-only idempotency, replay consistency). Strengthened #L1 acceptance criteria with rule-isolation requirements. (Spec §6.9 also adds discipline criterion for new judge call sites.)
> **Changes from v1**: Added #C0 (contract freeze), #K5 (orchestrate parity tests), #L8 (babysit parity tests). Updated #J1 with explicit non-goals. Updated #P5/#P6 to gate on parity suites. Updated #Q1 with integration-bug observation acceptance criteria.

---

## Index

42 issues across 9 tracks (including the C0 contract-freeze track and the K5/L8 parity-test issues), assignable to 6 parallel agents.

| # | Title | Track | Agent | Depends on |
|---|---|---|---|---|
| C0 | Runtime and validator contract freeze | C0 | J1 | — |
| J1 | `atdd coach` MVP — state machine skeleton (narrow non-goals) | J | J1 | C0 |
| J2 | `atdd agent` CLI subcommands | J | J1 | C0, J1 |
| J3 | Decision and judgment durability (jsonl logs) | J | J1 | C0, J1 |
| J4 | Two-phase commit (worktrees, launch) absorbed from orchestrate | J | J1 | J1, J3 |
| J5 | Runtime watcher (inotify/fswatch + git watcher + liveness) | J | J1 | J1, J3 |
| J6 | Resume from decisions log | J | J1 | J3, J4 |
| K1 | `atdd spawn` skeleton wrapping session_template render | K | K1 | C0, J1, J2 |
| K2 | Substrate spawn-harness blocks (wmbt_rules, train_rules, security_rules) | K | K1 | K1 |
| K3 | Canonical-naming + layout pass at spawn (absorbed from orchestrate) | K | K1 | K1 |
| K4 | Per-LLM convention file generation (CLAUDE.md, AGENTS.md, GLM.md) | K | K1 | K1 |
| **K5** | **Orchestrate parity test suite** | K | K1 | J4, K1, K3 |
| L1 | `atdd observer` skeleton + correction injection paths | L | L1 | C0, J1, J2 |
| L2 | Basic observer rules 01–05, 08, 09 | L | L1 | L1 |
| L3 | Token-threshold rule 06 (absorbed from babysit) | L | L1 | L1 |
| L4 | Babysit-absorbed rules 13–16 (bash auto-approve, naming/layout drift, smoke skip) | L | L1 | L1 |
| L5 | Substrate-aware rules 10, 11, 12, 17 | L | L1 | L1 |
| L6 | `atdd observer status` dashboard (absorbed from babysit) | L | L1 | L1 |
| L7 | `atdd observer aggregate-approve` (absorbed from babysit) | L | L1 | L1 |
| **L8** | **Babysit parity test suite** | L | L1 | L1, L3, L4, L6, L7 |
| M1 | Git watcher + commit trailer parsing | M | M1 | C0, J1, J3 |
| M2 | Custom pytest plugin for Violation collection | M | M1 | M1 |
| M3 | Validator selection per phase (toolkit + substrate v12) | M | M1 | M2 |
| M4 | Suppression scanner integration | M | M1 | M3 |
| M5 | Risk score with repo archetype slice | M | M1 | M3 |
| N1 | Reviewer persona + no-write spawn adapter | N | N1 | K2, M3 |
| N2 | Review-report schema (rule-ID-first, AC-coverage hard rule) | N | N1 | N1 |
| N3 | Per-phase reviewer prompts | N | N1 | N1 |
| N4 | Judge call site #2 (reviewer concern verdict) | N | N1 | N1, O1 |
| N5 | `atdd agent review` | N | N1 | N1, N2 |
| O1 | `atdd judge` core | O | O1 | C0, J1 |
| O2 | Judge call sites 1, 3, 4 (borderline tier-1, retry-vs-escalate, regression scope) | O | O1 | O1, M5 |
| O3 | Judge call site 5 (issue review aggregate ambiguity) | O | O1 | O1, O5 |
| O4 | Judge call site 6 (superseded rule-ID consolidation) | O | O1 | O1 |
| O5 | `atdd issue review` multi-pass cross-LLM | O | O1 | O1 |
| P1 | `atdd rules` discovery: show, where, grep | P | P1 | J1 |
| P2 | `atdd rules` discovery: disposition, archetype, suppressions | P | P1 | P1 |
| P3 | Per-LLM convention file generation in `atdd sync` | P | P1 | K4 |
| P4 | Config loader extensions for `coach.*` block | P | P1 | J1 |
| P5 | Decommission `atdd orchestrate` | P | P1 | All J/K absorption + **K5 passing on CI** |
| P6 | Decommission `atdd babysit` | P | P1 | All L absorption + **L8 passing on CI** |
| Q1 | End-to-end coach-driven cycle (with integration-bug observation) | Q | merge | All other tracks |

C0 lands first. After C0 and J1, all other tracks run in parallel. Q is the coach's done-line.

---

## Track C0 — Contract freeze (Agent J1, FIRST)

### Issue #C0 — Runtime and validator contract freeze

**Labels**: `coach`, `track-c0`, `wave-w0`, `coordination`

**Scope**

This is the coordination prerequisite for all parallel tracks. Six agents working simultaneously need stable schemas for the artifacts they produce and consume. Without explicit contracts, every cross-track interface is a potential merge conflict.

Produces a documentation-and-schemas-only PR (no behavior) at `src/atdd/coach/schemas/`:

- **`runtime-event.schema.json`** — every event type the runtime watcher emits (#J5 produces, #L1/#M1 consume). Event types: `agent_spawned`, `heartbeat`, `commit_observed`, `event_emitted`, `escalation_emitted`, `pr_opened`, `pr_closed`, `validation_pending`, `validation_complete`, `review_complete`, `correction_emitted`, `process_silence`. Each has shape `{event_type, agent_id?, timestamp, payload: {...}}`.
- **`coach-decision.schema.json`** — formalized from #J3 spec text. Append-only entries for `decisions.jsonl` (state transitions, configuration choices, escalations). Required fields: `decision_id`, `timestamp`, `coach_run_id`, `issue_number`, `decision_type`, `inputs`, `outcome`.
- **`coach-judgment.schema.json`** — formalized from #J3. Append-only for `judgments.jsonl`. Required: `judgment_id`, `timestamp`, `call_site` (one of the six per spec §6.9), `inputs_hash`, `response`, `cached` (bool).
- **`correction.schema.json`** — observer correction payloads (#L1 produces, #J5 consumes). Fields: `agent_id`, `rule_id`, `severity`, `disposition`, `correction_text`, `injection_method` (cli-return/multiplexer-send/respawn).
- **`validator-result.schema.json`** — formalized from spec §7.5. Aligns with substrate's `Violation` dataclass. Fields: `validator_id`, `rule_id`, `severity`, `disposition`, `location`, `detail`, `suppression_marker`. Used by #M2 (writer) and #N2/#O2 (readers).
- **`runtime-layout.md`** — the directory/file structure under `.atdd/runtime/` documented as a contract: `agents/<id>/heartbeat.json`, `agents/<id>/output.log`, `agents/<id>/events.jsonl`, `agents/<id>/corrections.jsonl`, `coach/decisions.jsonl`, `coach/judgments.jsonl`, `validations/<sha>/violations.jsonl`, `validations/<sha>/risk-score.json`, `validations/<sha>/suppressed.jsonl`, `validations/<sha>/stale-suppressions.jsonl`. Each file's role, who writes, who reads, append-only or rewritten, JSON-line vs single-doc.
- **`validator-invocation.md`** — how coach invokes the substrate pytest plugin. Fields: pytest CLI flags, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` policy, timeout per phase, retry-on-subprocess-crash policy (vs test-failure — different signal handling), env vars passed through.
- **`event-semantics.md`** — temporal contracts for every event type defined in `runtime-event.schema.json`. Schemas freeze *shape*; this document freezes *semantics*. For each of the 12 event types (`agent_spawned`, `heartbeat`, `commit_observed`, `event_emitted`, `escalation_emitted`, `pr_opened`, `pr_closed`, `validation_pending`, `validation_complete`, `review_complete`, `correction_emitted`, `process_silence`), specify:
  - **Producer** — which component emits (file watcher, git watcher, agent CLI, observer, etc.).
  - **Triggering condition** — the precise state change that emits.
  - **Idempotency contract** — at-least-once vs exactly-once delivery; whether consumers must dedupe.
  - **Ordering guarantees** — per-agent total order, cross-agent partial order, or none.
  - **Replay behavior** — on coach `--resume`, does this event re-fire? Is it cached? Idempotently re-applied?
  Without this artifact, parallel tracks would each form different temporal assumptions; concurrency bugs would surface only at #Q1.

Note: schemas reference but do NOT redefine substrate's `Violation` and `RuleMetadata` (they're stable Python dataclasses with established contracts). C0 is the boundary at which coach-internal artifacts are formalized.

**Acceptance criteria**

- All six schemas exist as committed files at `src/atdd/coach/schemas/`.
- Each schema has at least one valid example fixture committed alongside.
- `runtime-layout.md`, `validator-invocation.md`, and `event-semantics.md` are reviewed and approved by all track owners (J1, K1, L1, M1, N1, O1, P1) before merge — this is the coordination signal.
- A CI job validates that any future PR touching the schema files updates the corresponding fixtures.

**Dependencies**: None — entry point of the coach implementation.

**References**: §3.2, §4.4, §4.5, §6.4, §7.5, §7.7, §11.1.

---

## Track J — Coach state machine + agent CLI (Agent J1, after #C0)

### Issue #J1 — `atdd coach` MVP: state machine skeleton (narrow non-goals)

**Labels**: `coach`, `track-j`, `wave-w1`

**Scope**

Implements §4 coach state machine (skeleton ONLY) and §5.1 `atdd coach` CLI argparse.

- Create `src/atdd/coach/commands/coach.py` with the `atdd coach <issue-numbers...>` entry point.
- Implement state-machine enum: `INIT | PLANNED | RED | GREEN | SMOKE | REFACTOR | COMPLETE | BLOCKED | MERGED`.
- Implement state transition *table* (which states can transition to which).
- Implement the *CLI argparse skeleton* per §5.1: parse all flags, validate, print resolved configuration.
- Reuse `compute_waves` from `commands/orchestrate.py` for multi-issue ordering (§4.3).

**Non-goals (explicit, to prevent scope creep)**

This issue does NOT implement:

- Watcher attachment (#J5).
- Validator dispatch (#M3).
- Observer integration (#L1).
- Spawn integration (#K1).
- Per-state transition logic (handled in per-state issues across tracks).
- Two-phase commit (#J4).
- Decision durability (#J3 — though structure designed in C0 informs the skeleton).
- Resume (#J6).

J1 is intentionally narrow. State transitions wire as follow-ups; the skeleton's job is to give every parallel track a stable hook point.

**Acceptance criteria**

- `atdd coach 358` initializes a state machine in `INIT` for issue 358 and prints the planned state path (without executing transitions).
- `atdd coach 358 359 360 --strict-deps` resolves dependency graph and computes waves.
- All flags from §5.1 parse correctly.
- Unit tests demonstrating state-transition table correctness.
- Code review confirms no scope leak into J5/M3/L1/K1/J4/J3/J6 territory.

**Dependencies**: #C0.

**References**: §4, §5.1.

---

### Issue #J2 — `atdd agent` CLI subcommands

**Labels**: `coach`, `track-j`, `wave-w1`

**Scope**

Implements §5.3 `atdd agent` subcommands.

- Create `src/atdd/coach/commands/agent.py` with subcommands: `heartbeat`, `event`, `commit`, `ask`, `escalate`, `done`, `context`, `review`.
- Each subcommand writes to `.atdd/runtime/agents/<id>/` per §3.2 layout.
- `atdd agent commit --phase <P> --message "..."` writes commit trailers and calls `atdd checkpoint` (existing).
- `atdd agent ask` produces structured questions in `questions.jsonl`; coach answers via `answers/<id>.json`.

**Acceptance criteria**

- All subcommands resolve and write expected files.
- `atdd agent heartbeat` writes `.atdd/runtime/agents/<id>/heartbeat.json` with current timestamp.
- `atdd agent commit` produces a commit with all required trailers (`Agent-Id`, `Issue`, `WMBT-Urn`, `Phase`).

**Dependencies**: #J1.

**References**: §5.3, §3.2, §7.3.

---

### Issue #J3 — Decision and judgment durability (jsonl logs)

**Labels**: `coach`, `track-j`, `wave-w1`

**Scope**

Implements §4.5 decision durability and §6.9 judgment log.

- Append every coach state transition to `.atdd/runtime/coach/decisions.jsonl` *before* the action runs.
- Append every `atdd judge` call to `.atdd/runtime/coach/judgments.jsonl`.
- Define schemas at `src/atdd/coach/schemas/coach-decision.schema.json` and `coach-judgment.schema.json`.
- All actions remain idempotent (so resume works without double-execution).

**Acceptance criteria**

- A coach run writes decisions to `decisions.jsonl` in append-only fashion.
- A coach run with `atdd judge` calls writes to `judgments.jsonl`.
- Schema validation runs at write time.

**Dependencies**: #J1.

**References**: §4.5, §6.9, §7.7.

---

### Issue #J4 — Two-phase commit (worktrees, launch) absorbed from orchestrate

**Labels**: `coach`, `track-j`, `wave-w1`, `absorbed`

**Scope**

Implements §4.6 two-phase commit by absorbing `commands/orchestrate.py`.

- Move `_create_worktree`, `_remove_worktree`, the Phase A creation loop with rollback, and the Phase B launch loop into `coach.py`.
- Replace `.atdd/orchestrate-state.json` with `decisions.jsonl` as the durable resume source.
- Preserve rollback discipline: any worktree creation failure rolls back all already-created worktrees before exit.
- `commands/orchestrate.py` stays in place for now; #P5 decommissions it.

**Acceptance criteria**

- Coach with multiple issues creates all worktrees in Phase A; if any fail, all roll back.
- `atdd coach --resume <run-id>` reconstructs from `decisions.jsonl` and skips already-created worktrees.
- Existing orchestrate behavior preserved at parity.

**Dependencies**: #J1, #J3.

**References**: §4.6, §0.2 absorption inventory.

---

### Issue #J5 — Runtime watcher (inotify/fswatch + git watcher + liveness)

**Labels**: `coach`, `track-j`, `wave-w2`

**Scope**

Implements §4.4 event sources.

- Runtime watcher: `inotify`/`fswatch` on `.atdd/runtime/agents/*/`. On file change, parse the file (heartbeat, event, escalation, etc.) and push event to coach state machine.
- Git watcher: `inotify` on each worktree's `.git/refs/heads/`, plus `gh pr view` polling for PR state.
- Liveness checker: timer every 30s. Flags agents with stale process heartbeat.
- All three watchers run as concurrent threads; events feed a single coach event queue.

**Acceptance criteria**

- A file change in `.atdd/runtime/agents/<id>/` triggers a coach event within 1s.
- A git commit on a worktree branch triggers a `commit_observed` event.
- An agent with no process heartbeat for >`process_silence_seconds` triggers a `stuck` event.
- **Watcher reattachment**: kill the watcher process mid-run, restart it, verify no events are lost from disk-persisted state and no events are duplicated for in-flight transitions. Per `event-semantics.md` reattachment contract.
- **Duplicate suppression**: under simulated event-burst conditions (rapid file writes), each event arrives at the coach state machine exactly once per its idempotency contract. Events specified as at-least-once trigger correct dedup at the consumer; events specified as exactly-once never re-fire.
- **Append-only idempotency**: concurrent writes to `decisions.jsonl` from the watcher and the coach main loop don't interleave partial records. fsync+append discipline preserved.
- **Replay consistency on `--resume`**: after coach restart, the runtime watcher reconstructs its state from on-disk files and resumes event delivery without re-emitting events whose handlers have already completed (per the replay contracts in `event-semantics.md`).

**Dependencies**: #J1, #J3.

**References**: §4.4.

---

### Issue #J6 — Resume from decisions log

**Labels**: `coach`, `track-j`, `wave-w2`

**Scope**

Implements `--resume <run-id>` per §4.5.

- Coach reconstructs state-machine positions for each issue from `decisions.jsonl`.
- Skips actions that have already been logged as completed (idempotency).
- Re-attaches to runtime watchers without losing event stream.

**Acceptance criteria**

- Coach killed mid-run resumes correctly with `--resume`.
- Duplicate state transitions are not written.
- Watcher state reconstructs from on-disk `.atdd/runtime/`.

**Dependencies**: #J3, #J4.

**References**: §4.5.

---

## Track K — Spawn + canonical naming (Agent K1, after #J1, #J2)

### Issue #K1 — `atdd spawn` skeleton wrapping session_template render

**Labels**: `coach`, `track-k`, `wave-w1`

**Scope**

Implements §5.2 `atdd spawn` and §7.1 spawn-harness skeleton.

- Create `src/atdd/coach/commands/spawn.py` with `atdd spawn` CLI per §5.2.
- Wrap `session_template.py::render` (existing) and write to `<worktree>/.launch_prompt.txt`.
- Launch via the multiplexer abstraction (`get_multiplexer`, `new_workspace`/`new_surface`).
- Adapter selection: `--llm claude-code` calls `claude --dangerously-skip-permissions "$(cat <prompt>)"`. Other LLMs as separate adapters in K-track follow-ups.
- Emit `agent_spawned` event to runtime.

**Acceptance criteria**

- `atdd spawn --persona coder --llm claude-code --worktree <path> --issue 358 --agent-id coder-358-001 --runtime <path>` launches a session.
- `.launch_prompt.txt` exists at the worktree.
- Multiplexer surface is created; ref returned and logged.

**Dependencies**: #J1, #J2.

**References**: §5.2, §7.1.

---

### Issue #K2 — Substrate spawn-harness blocks (wmbt_rules, train_rules, security_rules)

**Labels**: `coach`, `track-k`, `wave-w1`, `substrate-integration`

**Scope**

Implements §7.1 substrate v12 §8.2 spawn blocks.

- Extend `src/atdd/coach/commands/spawn_harness_blocks.py` with `render_wmbt_rules_block(rules, *, coach_phase)` and `render_train_rules_block(rules, *, coach_phase)` parallel to the existing `render_security_rules_block`.
- Field mapping per substrate v12 §8.2 (matches the existing security renderer's pattern).
- Spawn (#K1) calls all three renderers and includes the blocks in the launch prompt under sections `wmbt_rules:`, `train_rules:`, `security_rules:`.
- Phase filtering: only rules whose `RuleMetadata.phase` matches the coach's current phase are included.

**Acceptance criteria**

- `render_wmbt_rules_block` produces output structurally matching substrate v12 §8.2 example.
- `render_train_rules_block` ditto.
- Spawn prompt for an agent at GREEN includes `wmbt_rules:` block listing only `phase: GREEN` rules in scope.
- Unit tests against fixture `RuleMetadata` instances.

**Dependencies**: #K1.

**References**: §7.1, substrate v12 §8.2.

---

### Issue #K3 — Canonical-naming + layout pass at spawn (absorbed from orchestrate)

**Labels**: `coach`, `track-k`, `wave-w1`, `absorbed`

**Scope**

Implements §7.1.5 by absorbing `apply_canonical_name_and_layout` from `commands/orchestrate.py`.

- Move the function into a coach module (e.g., `src/atdd/coach/utils/session_naming_apply.py`).
- `atdd spawn` calls it after `new_workspace`/`new_surface`.
- Best-effort: rename failures don't crash spawn; observer rule `14-canonical-naming-drift` (#L4) re-applies on subsequent ticks.
- Emits `coach.orchestration.canonical-session-name` rule-ID on rename action.

**Acceptance criteria**

- After `atdd spawn`, the multiplexer surface has the canonical name (e.g. `FORGE358-coder`).
- `/rename <name>\n` is sent into the running agent so in-conversation header matches.
- Layout target label is printed.
- Unit tests against a fake multiplexer backend.

**Dependencies**: #K1.

**References**: §7.1.5, §0.2 absorption inventory.

---

### Issue #K4 — Per-LLM convention file generation (CLAUDE.md, AGENTS.md, GLM.md)

**Labels**: `coach`, `track-k`, `wave-w2`

**Scope**

Implements §7.1 per-LLM convention file extension.

- Generator at `src/atdd/coach/templates/persona/<llm>/<file>.md.tmpl`.
- Output files: `CLAUDE.md`, `AGENTS.md`, `GLM.md` (and `GEMINI.md` aliased to `AGENTS.md`).
- Include the rule-ID grammar section and `bind_rule()` contract per §7.1.
- Hook into `atdd sync` (existing); see also #P3 for sync integration.

**Acceptance criteria**

- `atdd sync` regenerates all four files in the repo root.
- Each file embeds the `<archetype>.<convention_short_name>.<rule_name>` grammar.
- Each file embeds the `bind_rule()` contract example.

**Dependencies**: #K1.

**References**: §7.1.

---

### Issue #K5 — Orchestrate parity test suite

**Labels**: `coach`, `track-k`, `wave-w3`, `parity-test`, `gating-decommission`

**Scope**

Operationalizes the "behavior parity" claim made by the orchestrate-absorbing issues (#J4 two-phase commit, #K1 spawn skeleton, #K3 canonical naming). Without this issue, parity is a review-time judgment call; with it, parity is CI-enforced equivalence.

- Create fixture-driven test suite at `tests/integration/test_orchestrate_coach_parity.py`.
- Each fixture defines an `atdd orchestrate <args>` invocation and the expected `atdd coach <equivalent args>` invocation.
- Both invocations run against a shared fixture worktree state (multiplexer mock backend, fake gh CLI returning fixed issue bodies).
- Assert equivalence on observable outputs:
  - **Worktree creation** order, paths, branches.
  - **Multiplexer dispatch** — backend, mode, surfaces created.
  - **Canonical naming** — names applied to surfaces.
  - **Session prompts** — `.launch_prompt.txt` contents byte-equivalent (modulo timestamps).
  - **State file** — `orchestrate-state.json` (orchestrate) vs `decisions.jsonl` (coach) carry semantically equivalent information; document the field-by-field mapping in a `tests/integration/parity-fixtures/orchestrate-coach.md` reference.
- Differences that are NOT failures: state file format (jsonl vs json), additional logging, additional decision entries that have no orchestrate equivalent (e.g., observer hookup events).
- CI fails this suite → #P5 cannot land.

**Acceptance criteria**

- At least 5 fixture scenarios covering: single issue, multi-issue with deps, resume case, worktree creation failure with rollback, multiplexer-mode pane.
- All fixtures pass on CI.
- Differences-allowed list documented.
- The suite runs in <60s on a developer machine.

**Dependencies**: #J4 (two-phase commit absorbed), #K1 (spawn skeleton), #K3 (canonical naming pass).

**References**: §11.3, §0.2 absorption inventory.

---

## Track L — Observer + absorbed babysit machinery (Agent L1, after #J1, #J2)

### Issue #L1 — `atdd observer` skeleton + correction injection paths

**Labels**: `coach`, `track-l`, `wave-w1`

**Scope**

Implements §5.4 `atdd observer` and §8.1, §8.2 observer architecture.

- Create `src/atdd/coach/commands/observer.py` with subcommands `run`, `attach`, `status`, `aggregate-approve`.
- `atdd observer run --agent-id <id>` tails `output.log`, watches worktree, runs detection rules.
- Three correction injection paths per §8.2: CLI return-path (default), multiplexer send-keys, kill-and-respawn.
- Rule registry: `.atdd/observer/rules/*.yaml` discoverable.

**Acceptance criteria**

- `atdd observer run` starts and tails the agent log file.
- A simulated detection rule fires and writes to `corrections.jsonl`.
- `atdd observer attach --agent-id <id>` prints recent observations.
- **Rule failure isolation**: each rule loads, evaluates, and emits independently. A rule that raises an unhandled exception is logged with its rule_id, marked as faulty for the run, and does NOT crash the observer process or affect other rules' evaluation.
- **Rule loading is order-independent**: rules in `.atdd/observer/rules/` are loaded in alphabetical order but evaluation order does not affect outcome; rules cannot depend on side effects of other rules' evaluation.
- **Rule-level errors are surfaced**: a faulty rule produces a one-time warning to stderr and an entry in `corrections.jsonl` with `meta: rule_load_error` so operators see the failure rather than silently missing detections.

**Dependencies**: #J1, #J2.

**References**: §5.4, §8.1, §8.2.

---

### Issue #L2 — Basic observer rules 01–05, 08, 09

**Labels**: `coach`, `track-l`, `wave-w1`

**Scope**

Implements seven observer rules from §8.3:

- `01-unstructured-question`
- `02-token-silence`
- `03-completion-claim-without-commit`
- `04-out-of-scope-edit` (with `.atdd/` clause from babysit's `detect_violation`)
- `05-missed-heartbeat`
- `08-reviewer-edit-attempt`
- `09-validator-failure-ignored`

Each rule lives at `.atdd/observer/rules/<NN>-<slug>.yaml`.

**Acceptance criteria**

- Each rule's trigger and correction matches §8.3 table.
- Unit tests with synthetic agent outputs demonstrating fire/no-fire for each rule.

**Dependencies**: #L1.

**References**: §8.3 (rules 01–05, 08, 09).

---

### Issue #L3 — Token-threshold rule 06 (absorbed from babysit)

**Labels**: `coach`, `track-l`, `wave-w1`, `absorbed`

**Scope**

Implements observer rule `06-token-threshold` by absorbing `load_token_alert_threshold`, `read_token_count`, `check_token_threshold` from `commands/babysit.py`.

- Move the three functions into a coach observer module.
- Default threshold 400k from `coach.token_alert_threshold` config.
- Observer rule fires when `read_token_count` exceeds threshold; correction text per §8.3.

**Acceptance criteria**

- A simulated context-status >400k fires the rule.
- Config override at `coach.token_alert_threshold: 350000` lowers threshold.
- Existing babysit behavior preserved at parity.

**Dependencies**: #L1.

**References**: §8.3 (rule 06), §0.2 absorption inventory.

---

### Issue #L4 — Babysit-absorbed rules 13–16 (bash auto-approve, naming/layout drift, smoke skip)

**Labels**: `coach`, `track-l`, `wave-w2`, `absorbed`

**Scope**

Implements four observer rules absorbing `classify_prompt`, `correct_naming_drift`, `correct_layout_drift`, `detect_violation` from `commands/babysit.py`.

- Rule `13-bash-auto-approve`: reads `orchestration.convention.yaml::babysit.bash_auto_approve_patterns.rules` and `bash_deny_patterns.rules`. On match against approve patterns, auto-approves; on match against deny, escalates. Reuses `_load_bash_patterns` and `BashPattern`.
- Rule `14-canonical-naming-drift`: on each tick, compares surface name to canonical via `is_canonical_name`. If drifted, calls `correct_naming_drift`. Logs `coach.orchestration.canonical-session-name`.
- Rule `15-layout-drift`: on each tick, compares surface count + arrangement to `target_grid_label`. If drifted, calls `correct_layout_drift`. Logs `coach.orchestration.layout-conformance`.
- Rule `16-smoke-skip`: detects `--status REFACTOR` without prior SMOKE per babysit's existing `detect_violation`.

**Acceptance criteria**

- Each rule's behavior parity with current babysit equivalent.
- Bash patterns file unchanged; rule loads and applies them correctly.
- Naming drift on a renamed surface re-applies canonical name within one tick.
- Smoke-skip detection fires on the same screen patterns as today.

**Dependencies**: #L1.

**References**: §8.3 (rules 13–16), §0.2 absorption inventory.

---

### Issue #L5 — Substrate-aware rules 10, 11, 12, 17

**Labels**: `coach`, `track-l`, `wave-w2`, `substrate-integration`

**Scope**

Implements four substrate-aware observer rules from §8.3:

- `10-stale-suppression-detected` (toolkit conventions only — repo rules unsuppressible per substrate v12)
- `11-unbound-rule-id-in-validator`
- `12-rule-id-grammar-violation`
- `17-repo-rule-disposition-declared` (substrate v12 alignment — agents must not declare disposition on repo YAML)

**Acceptance criteria**

- Rule 10 fires when commit touches a file with stale `# atdd:suppress(<rule_id>) [UNTIL=past]` marker; uses existing `find_stale_suppressions`. Does NOT fire for `repo.*` rule IDs.
- Rule 11 fires when an agent creates a validator missing `bind_rule()` call.
- Rule 12 fires on non-canonical rule-IDs.
- Rule 17 fires when an agent's diff adds `disposition:` field to any acceptance or abuse_case YAML.

**Dependencies**: #L1.

**References**: §8.3 (rules 10–12, 17), substrate v12 §2, §4.4.

---

### Issue #L6 — `atdd observer status` dashboard (absorbed from babysit)

**Labels**: `coach`, `track-l`, `wave-w2`, `absorbed`

**Scope**

Implements `atdd observer status` per §5.4 by absorbing `_render_dashboard`, `SurfaceRow`, `_format_hms`, `_extract_surface_state` from `commands/babysit.py`.

- Move dashboard rendering into the observer command.
- Output parity with current babysit dashboard.
- Reads from `.atdd/runtime/agents/*/` rather than polling multiplexer state directly.

**Acceptance criteria**

- `atdd observer status` prints a per-surface table with name, phase, last-heartbeat, token count.
- Parity with `atdd babysit` dashboard at time of decommissioning.

**Dependencies**: #L1.

**References**: §5.4, §0.2 absorption inventory.

---

### Issue #L7 — `atdd observer aggregate-approve` (absorbed from babysit)

**Labels**: `coach`, `track-l`, `wave-w2`, `absorbed`

**Scope**

Implements `atdd observer aggregate-approve [--scope <ids>]` per §5.4 by absorbing `aggregate_approve` and `AggregateApprovalResult` from `commands/babysit.py`.

- Move the function into the observer command.
- Operator runs `atdd observer aggregate-approve` to batch-approve known-safe prompts across active sessions.
- Reads bash patterns via the same path as rule 13 (#L4).

**Acceptance criteria**

- `atdd observer aggregate-approve --scope 358,359` approves matching prompts in those issues' sessions.
- Output parity with current babysit equivalent.

**Dependencies**: #L1.

**References**: §5.4, §0.2 absorption inventory.

---

### Issue #L8 — Babysit parity test suite

**Labels**: `coach`, `track-l`, `wave-w3`, `parity-test`, `gating-decommission`

**Scope**

Operationalizes "behavior parity" for the babysit-absorbing issues (#L3 token threshold, #L4 bash auto-approve + naming/layout drift + smoke skip, #L6 dashboard, #L7 aggregate-approve). Mirror discipline of #K5.

- Create fixture-driven test suite at `tests/integration/test_babysit_observer_parity.py`.
- Each fixture defines a babysit invocation against a fake multiplexer state and the expected `atdd observer` equivalent.
- Assert equivalence on observable outputs:
  - **Token-alert firing** — given a fake `claude --print-context-status` output, both fire the alert at the same threshold.
  - **Bash-pattern auto-approval** — given a screen with a known-safe prompt, both approve; with a deny pattern, both escalate.
  - **Naming drift correction** — given a renamed surface, both detect drift and re-apply canonical name within one tick.
  - **Layout drift correction** — given a non-conforming surface arrangement, both correct it.
  - **Smoke-skip detection** — given a screen showing `--status REFACTOR` without prior SMOKE, both flag the violation.
  - **Dashboard rendering** — given a fake set of surfaces, both produce the same row content (modulo trailing whitespace).
  - **Aggregate-approve** — given multiple surfaces with auto-approvable prompts, both approve the same set.
- Differences that are NOT failures: corrections.jsonl additions (coach-side richer logging), dashboard-format minor whitespace, internal state representation changes.
- CI fails this suite → #P6 cannot land.

**Acceptance criteria**

- At least 7 fixture scenarios covering each absorbed function category.
- All fixtures pass on CI.
- Differences-allowed list documented.
- The suite runs in <60s on a developer machine.

**Dependencies**: #L1 (observer skeleton), #L3 (token threshold), #L4 (bash auto-approve, naming/layout drift, smoke skip), #L6 (dashboard), #L7 (aggregate-approve).

**References**: §11.3, §0.2 absorption inventory.

---

## Track M — Tier-1 validator dispatch (Agent M1, after #J1, #J3)

### Issue #M1 — Git watcher + commit trailer parsing

**Labels**: `coach`, `track-m`, `wave-w2`

**Scope**

Implements §6.4 step 1 commit observation.

- Git watcher emits `commit_observed` events with `{worktree, sha, parent_sha}`.
- Parse trailers via `git log -1 --format=%B <sha>`: extract `Phase`, `WMBT-Urn`, `Agent-Id`, `Issue`.
- Emit `validation_pending` event for the trailer-resolved (phase, scope).

**Acceptance criteria**

- A new commit on a watched branch triggers a coach event with parsed trailers within 1s.
- Missing trailers produce a `coach.commit-trailers.*` violation routed via tier-1 (handled by existing pre-commit hook in production; here for completeness).

**Dependencies**: #J1, #J3.

**References**: §6.4 (steps 1, 2).

---

### Issue #M2 — Custom pytest plugin for Violation collection

**Labels**: `coach`, `track-m`, `wave-w2`

**Scope**

Implements §6.4 step 4 Violation collection.

- Create `src/atdd/coach/runtime/violation_collector.py` as a pytest plugin.
- Plugin hooks: `pytest_runtest_logreport` (capture `Violation` records emitted via `assert_disposition_satisfied`).
- Writes records to `.atdd/runtime/validations/<sha>/violations.jsonl`.
- Coach invokes pytest with `-p atdd.coach.runtime.violation_collector` against selected validator paths.

**Acceptance criteria**

- A pytest run with the plugin captures all `Violation` records emitted in that run.
- `violations.jsonl` content matches the schema at `validator-result.schema.json`.

**Dependencies**: #M1.

**References**: §6.4 (steps 3, 4), §7.5.

---

### Issue #M3 — Validator selection per phase (toolkit + substrate v12)

**Labels**: `coach`, `track-m`, `wave-w2`, `substrate-integration`

**Scope**

Implements §6.5 phase-driven dispatch including substrate v12 alignment.

- Build the validator set per phase by union of:
  - Toolkit conventions per the §6.5 mapping table (planner, tester, coder, smoke-tester, refactor-strict).
  - Repo rules whose `bind_rule(rule_id).phase` matches the current coach phase, regardless of source kind.
- Substrate enforcement validators (`tester.acceptance-violation.*`) included at PLANNED.
- Selection overrideable via `.atdd/coach/config.yaml::coach.validators.selection`.

**Acceptance criteria**

- A coach session at GREEN selects all repo rules with `phase: GREEN` (WMBT, train, security all considered).
- A coach session at PLANNED runs the substrate enforcement validators.
- Override path correctly substitutes a project-specific selection.

**Dependencies**: #M2.

**References**: §6.5, substrate v12 §8.1.

---

### Issue #M4 — Suppression scanner integration

**Labels**: `coach`, `track-m`, `wave-w2`

**Scope**

Implements §6.4 step 5 and §6.6.

- Run `find_suppressions()` over the worktree; for each violation, check `(rule_id, location)`.
- Suppressed violations move to `.atdd/runtime/validations/<sha>/suppressed.jsonl`.
- Run `find_stale_suppressions()`; output to `stale-suppressions.jsonl`.
- Repo-rule violations skip the suppression check (always strict, scanner output ignored for them — already correct via `disposition_gate`).

**Acceptance criteria**

- A `suppress-and-clean` toolkit violation with a matching marker moves to `suppressed.jsonl`.
- A repo-rule violation never appears in `suppressed.jsonl` even if a marker exists.
- Stale suppression markers populate `stale-suppressions.jsonl`.

**Dependencies**: #M3.

**References**: §6.4 (step 5), §6.6.

---

### Issue #M5 — Risk score with repo archetype slice

**Labels**: `coach`, `track-m`, `wave-w2`, `substrate-integration`

**Scope**

Implements §6.8 risk score computation.

- Compute `risk_score = sum(severity for active_violations)`.
- Compute `by_archetype` breakdown including `repo` slice.
- Compute `by_severity`, `by_disposition`, `stale_suppressions` counts.
- Write to `.atdd/runtime/validations/<sha>/risk-score.json`.
- Schema at `risk-score.schema.json`.

**Acceptance criteria**

- A run with mixed toolkit and repo violations produces a breakdown with both slices.
- PR description (when COMPLETE in #Q1) includes the score and breakdown.
- Schema validation runs at write time.

**Dependencies**: #M3.

**References**: §6.8.

---

## Track N — Reviewer + review schemas (Agent N1, after #K2, #M3)

### Issue #N1 — Reviewer persona + no-write spawn adapter

**Labels**: `coach`, `track-n`, `wave-w3`

**Scope**

Implements §6.3 reviewer persona infrastructure.

- Spawn adapter variant for reviewer: strips commit/edit tools.
- System prompt forbids edits explicitly.
- Observer rule `08-reviewer-edit-attempt` (already in #L2) catches violations.
- Reviewer reads `target_commit` and produces a review report (#N2).

**Acceptance criteria**

- A reviewer agent spawned with `atdd spawn --persona reviewer` cannot run `git commit` or write to the worktree.
- Reviewer's only output channel is `atdd agent review --target-commit <sha> --report-file <path>`.

**Dependencies**: #K2, #M3.

**References**: §6.3.

---

### Issue #N2 — Review-report schema (rule-ID-first, AC-coverage hard rule)

**Labels**: `coach`, `track-n`, `wave-w3`

**Scope**

Implements §7.4 review-report schema.

- Schema at `src/atdd/coach/schemas/review-report.schema.json`.
- Hard rules per §7.4: `verdict` cannot be `pass` if any AC is `not_covered`; rule_id severity matches registry; verdict cannot be `pass` if any finding has `disposition: strict` AND `rule_id != null`.
- Schema validator runs at coach intake of every review report.

**Acceptance criteria**

- A review report violating any hard rule is rejected at intake with a clear error.
- Conforming reports parse and feed routing.

**Dependencies**: #N1.

**References**: §7.4.

---

### Issue #N3 — Per-phase reviewer prompts

**Labels**: `coach`, `track-n`, `wave-w3`

**Scope**

Implements §6.3 per-phase reviewer focus.

- Templates at `src/atdd/coach/prompts/persona/reviewer/<phase>.prompt.yaml` for PLANNED, RED, GREEN, SMOKE, REFACTOR.
- Each template embeds the rule-resolution block per §7.2.
- Reviewer template includes the `rules_in_scope` section computed by spawn.

**Acceptance criteria**

- Reviewer at PLANNED prompts on WMBT decomposition, acceptance specificity, dependencies.
- Reviewer at GREEN prompts on AC coverage, diff scope, implementation correctness.
- Each prompt includes the rule-ID resolution guidance.

**Dependencies**: #N1.

**References**: §6.3, §7.2.

---

### Issue #N4 — Judge call site #2 (reviewer concern verdict)

**Labels**: `coach`, `track-n`, `wave-w3`

**Scope**

Implements §6.9 call site #2.

- When reviewer returns `verdict: concern`, coach calls `atdd judge` with structured context.
- Schema at `judge-reviewer-concern.response.schema.json`.
- Judge response: `{decision: "block|annotate_and_continue", rationale, pr_annotation}`.
- Response feeds coach routing.

**Acceptance criteria**

- A reviewer `concern` verdict triggers exactly one judge call.
- Judge response routes to either block (back to phase) or annotate (continue with PR comment).
- Logged in `judgments.jsonl`.

**Dependencies**: #N1, #O1.

**References**: §6.9 (call site #2).

---

### Issue #N5 — `atdd agent review`

**Labels**: `coach`, `track-n`, `wave-w3`

**Scope**

Implements `atdd agent review --target-commit <sha> --report-file <path>` per §5.3.

- Reads `--report-file` and validates against `review-report.schema.json`.
- Writes to `.atdd/runtime/agents/<reviewer-id>/reviews/<review-id>.json`.
- Emits `review_complete` event.

**Acceptance criteria**

- A reviewer agent calling `atdd agent review` produces a written report and emits the event.
- Schema validation rejects malformed reports with rule-ID-bound errors.

**Dependencies**: #N1, #N2.

**References**: §5.3, §7.4.

---

## Track O — Judge + issue review (Agent O1, after #J1)

### Issue #O1 — `atdd judge` core

**Labels**: `coach`, `track-o`, `wave-w1`

**Scope**

Implements §5.5 `atdd judge` and §6.9 (core).

- Create `src/atdd/coach/commands/judge.py` with `atdd judge --prompt-template <yaml> --schema <json> --inputs key=val ...`.
- Reads prompt template, fills inputs, calls LLM, validates response against schema.
- Logs to `judgments.jsonl` per #J3.
- `coach.judge.fail_open` config: on LLM unavailable, use conservative fallback (escalate, block, retry).

**Acceptance criteria**

- `atdd judge --prompt-template foo.yaml --schema bar.json --inputs sha=abc123` returns a structured response or fails loudly.
- Fail-open behavior matches config.
- Log entry written for every call.

**Dependencies**: #J1.

**References**: §5.5, §6.9.

---

### Issue #O2 — Judge call sites 1, 3, 4 (borderline tier-1, retry-vs-escalate, regression scope)

**Labels**: `coach`, `track-o`, `wave-w2`

**Scope**

Implements §6.9 call sites 1, 3, 4.

- Call site #1: borderline tier-1 result (mixed pass/fail with ambiguous severity).
- Call site #3: retry-vs-escalate at threshold (before consuming final retry).
- Call site #4: cross-phase regression risk.
- Each has its own response schema.

**Acceptance criteria**

- Each call site triggers exactly when its conditions are met.
- Response schemas validate.
- Coach routing uses the response.

**Dependencies**: #O1, #M5.

**References**: §6.9 (call sites 1, 3, 4).

---

### Issue #O3 — Judge call site 5 (issue review aggregate ambiguity)

**Labels**: `coach`, `track-o`, `wave-w3`

**Scope**

Implements §6.9 call site #5.

- When `atdd issue review` returns mixed pass/concern across passes, coach calls judge to aggregate.
- Schema at `judge-issue-review-aggregate.response.schema.json`.
- Response: `{decision: "accept|request_revision|escalate", consolidated_feedback}`.

**Acceptance criteria**

- Mixed-verdict issue review triggers exactly one judge call.
- Coach routes per response.

**Dependencies**: #O1, #O5.

**References**: §6.9 (call site #5), §6.10.

---

### Issue #O4 — Judge call site 6 (superseded rule-ID consolidation)

**Labels**: `coach`, `track-o`, `wave-w3`

**Scope**

Implements §6.9 call site #6.

- When a Violation references a legacy alias whose canonical rule has `superseded_by` set, judge consolidates migration guidance for spawn-feedback.
- Schema at `judge-superseded-rule-consolidation.response.schema.json`.

**Acceptance criteria**

- A violation with a superseded rule-ID triggers the call site.
- Response feeds spawn-feedback (#K1) on next respawn.

**Dependencies**: #O1.

**References**: §6.7, §6.9 (call site #6).

---

### Issue #O5 — `atdd issue review` multi-pass cross-LLM

**Labels**: `coach`, `track-o`, `wave-w2`

**Scope**

Implements §5.6 and §6.10.

- Create `src/atdd/coach/commands/issue_review.py` with `atdd issue review <N> --passes 3 --llms ... --dimensions ...`.
- N independent passes (default 3, min 2), each by a different LLM.
- Five dimensions per pass: systemic, ambiguities, gap, regression, comprehensiveness.
- Aggregate output at `.atdd/runtime/issue-reviews/<N>/aggregate.json`.

**Acceptance criteria**

- `atdd issue review 358 --passes 3 --llms claude-haiku,gpt-5-mini,gemini-flash` runs three independent reviews.
- Aggregate identifies systemic concerns across passes.
- Pre-coach precondition (§4.2) reads the aggregate.

**Dependencies**: #O1.

**References**: §5.6, §6.10.

---

## Track P — Discovery, sync, config (Agent P1, after #J1)

### Issue #P1 — `atdd rules` discovery: show, where, grep

**Labels**: `coach`, `track-p`, `wave-w0`

**Scope**

Implements §5.7 first three subcommands.

- `atdd rules show <id>`: resolve rule via `bind_rule`; print full metadata.
- `atdd rules where <id>`: print validator `<module>::<function>` reference.
- `atdd rules grep <pattern>`: search descriptions, IDs, aliases.

**Acceptance criteria**

- All three subcommands resolve toolkit and repo rules transparently.
- `atdd rules show repo.govern-lifecycle.D003-acc-unit-001` returns substrate-derived metadata.

**Dependencies**: #J1.

**References**: §5.7.

---

### Issue #P2 — `atdd rules` discovery: disposition, archetype, suppressions

**Labels**: `coach`, `track-p`, `wave-w0`

**Scope**

Implements §5.7 remaining subcommands.

- `atdd rules disposition <strict|suppress-and-clean|advisory|documentation-only>`: list rules with the disposition.
- `atdd rules archetype <coder|coach|tester|planner|repo>`: list rules under archetype.
- `atdd rules suppressions [--stale-only] [--rule <id>]`: delegate to `suppression_scanner`.

**Acceptance criteria**

- `atdd rules archetype repo` lists all substrate-derived rules.
- `atdd rules disposition strict` lists all strict rules across registries.
- `atdd rules suppressions --stale-only` lists all expired markers.

**Dependencies**: #P1.

**References**: §5.7.

---

### Issue #P3 — Per-LLM convention file generation in `atdd sync`

**Labels**: `coach`, `track-p`, `wave-w2`

**Scope**

Implements §7.1 sync integration with #K4's templates.

- Hook `atdd sync` to regenerate per-LLM convention files using the templates from #K4.
- Verify rule-ID grammar and `bind_rule` contract sections render correctly.

**Acceptance criteria**

- `atdd sync` regenerates `CLAUDE.md`, `AGENTS.md`, `GLM.md` from templates.
- Repeated runs are idempotent.

**Dependencies**: #K4.

**References**: §7.1.

---

### Issue #P4 — Config loader extensions for `coach.*` block

**Labels**: `coach`, `track-p`, `wave-w0`

**Scope**

Implements §10 config loader.

- Extend `load_atdd_config` to parse the `coach:` block per §10 example.
- Add validation for new fields: `risk_thresholds`, `suppressions.honor`, `suppressions.block_on_stale`, `suppressions.grace_days`, `validators.selection`, `validators.grace_window_seconds`, `validators.pytest_args`, `judge.enabled`, `judge.fail_open`, `judge.log_full_inputs`.
- Default values match §10.

**Acceptance criteria**

- Coach reads config from `.atdd/config.yaml::coach` and applies defaults for missing fields.
- Invalid fields raise loud errors.

**Dependencies**: #J1.

**References**: §10.

---

### Issue #P5 — Decommission `atdd orchestrate`

**Labels**: `coach`, `track-p`, `wave-w4`, `decommission`

**Scope**

Implements §11.3 decommissioning of `atdd orchestrate`.

- Move `commands/orchestrate.py` to `commands/_archived/orchestrate.py`.
- Remove from CLI registry in `commands/__init__.py` (or wherever subcommands are registered).
- Add stub at `commands/orchestrate.py` that prints the migration message: `atdd orchestrate has been removed in coach v9. Use 'atdd coach <issue-numbers>' instead. Migration: every flag maps directly per atdd-coach-spec-v9.md §5.1.`
- Verify all callers have migrated (search codebase for `atdd orchestrate` invocations).
- Update CHANGELOG.

**Acceptance criteria**

- `atdd orchestrate <args>` prints the migration message and exits non-zero.
- No internal toolkit code paths call `atdd orchestrate` anymore.
- Orchestration convention file (rule-IDs) unchanged — still resolvable via `bind_rule()`.
- **#K5 parity suite passing on CI is a precondition for merge.** This is the operationalized "behavior parity" check; without it, decommissioning is a leap of faith.

**Dependencies**: All #J1, #J4, #K1, #K3 (worktree + naming + spawn absorption complete) AND #K5 passing on CI.

**References**: §11.3, §0.2.

---

### Issue #P6 — Decommission `atdd babysit`

**Labels**: `coach`, `track-p`, `wave-w4`, `decommission`

**Scope**

Implements §11.3 decommissioning of `atdd babysit`.

- Move `commands/babysit.py` to `commands/_archived/babysit.py`.
- Remove from CLI registry.
- Add stub printing: `atdd babysit has been removed in coach v9. Use 'atdd observer status' (dashboard), 'atdd observer aggregate-approve' (batch approve), or 'atdd coach' (end-to-end) per atdd-coach-spec-v9.md §0.2.`
- Update CHANGELOG.

**Acceptance criteria**

- `atdd babysit <args>` prints migration message and exits non-zero.
- All babysit machinery accessible through `atdd observer` or `atdd coach`.
- **#L8 parity suite passing on CI is a precondition for merge.** Operationalized parity check.

**Dependencies**: All #L1–#L7 (observer absorption complete) AND #L8 passing on CI.

**References**: §11.3, §0.2.

---

## Track Q — Integration acceptance (merge-window)

### Issue #Q1 — End-to-end coach-driven cycle (with integration-bug observation)

**Labels**: `coach`, `track-q`, `wave-w4`, `integration`

**Scope**

This is coach's done-line — analogous to substrate v12 #17. Critically, this is also the **first time substrate↔coach integration runs end-to-end**. Substrate is shipped, coach v8 components ship individually with unit tests, but the integration surface between them is unproven until #Q1 runs. Bugs are expected; the issue's job is to surface and document them.

- Pick one real GitHub issue (small scope, single WMBT, ideally one with both `harness.type` and `signal.metric` to exercise both substrate runner modes).
- Run `atdd coach <N>` from `INIT` through `COMPLETE` with a PR opened.
- **Enable verbose integration logging at the substrate↔coach boundary**: every validator invocation, every `bind_rule()` call from coach context, every spawn-harness block rendering, every gate verdict consumption logged at INFO level to `.atdd/runtime/coach/integration.log`.
- Verify the cycle produces:
  - Decision log at `decisions.jsonl`.
  - Validation outputs at `validations/<sha>/` for each commit.
  - Risk score with `repo` archetype slice if any repo rules trigger.
  - Reviewer report at each enabled phase.
  - PR with risk-score breakdown in description.
- Document the cycle in `docs/coach-worked-example.md`.
- **File integration bugs as discovered.** Any unexpected behavior at the substrate↔coach boundary becomes a follow-up issue against the appropriate track. This is expected, not a failure of #Q1; it's the explicit purpose of running the cycle.

**Acceptance criteria**

- A coach-driven cycle on the chosen issue completes with `COMPLETE` state.
- All artifacts populated.
- `integration.log` contains INFO-level entries for every substrate↔coach handoff.
- An agent (human or LLM) can read the artifacts and understand the cycle.
- `docs/coach-worked-example.md` exists.
- **An "integration bugs discovered" section in the worked example doc inventories any cross-boundary issues found and links to follow-up issues.** Empty section is acceptable; missing section is not.
- A noted expectation is documented: coach v8 may need an "integration hardening" milestone (sequence of follow-up PRs) before being declared production-ready beyond this worked example.

**Dependencies**: All other tracks (J1–J6, K1–K5, L1–L8, M1–M5, N1–N5, O1–O5, P1–P6).

**References**: §11.5, §11.6, full spec.

---

## Filing notes

- All issues should reference the spec at `atdd-coach-spec-v9.md` for context.
- **#C0 must land first**, before any other issue. It is the coordination prerequisite for parallel work — six agents agreeing on schemas up front prevents merge-conflict storms.
- Each issue's "Dependencies" section is the merge-order constraint, not a soft suggestion.
- Track Q (#Q1) is the coach's done-line. Until #Q1 passes, coach is not done — even if all upstream issues are individually closed.
- Issues marked `absorbed` move existing code from `commands/orchestrate.py` or `commands/babysit.py` into coach modules with no functional change. Behavior parity is the acceptance criterion.
- Issues marked `parity-test` (#K5, #L8) operationalize the parity claim with CI-enforced equivalence. They gate decommissioning issues (#P5, #P6).
- Issues marked `substrate-integration` consume substrate v12 (already shipped) — `RuleMetadata` extension, phase-driven dispatch, runners, spawn-harness blocks.
- Issues marked `decommission` (#P5, #P6) gate on all `absorbed` issues completing AND the corresponding parity test suite passing on CI. Hard cut, no `*-legacy` shim.
- Issues marked `gating-decommission` (#K5, #L8) are merge gates for `decommission` issues. Without them, "behavior parity" is a review-time judgment call; with them, parity is CI-enforced.
- Issues marked `coordination` (#C0) produce documentation/schemas with no behavior. They unblock parallel work but ship nothing user-facing.
- Self-hosting inflection (§11.5): after #M5 and #L4, coach can drive its own remaining issues. The team decides whether to dogfood from this point.
- Integration-bug expectation (§11.6): #Q1 will surface substrate↔coach integration bugs not catchable in unit tests. Plan a follow-up "integration hardening" milestone for the discovered issues.
