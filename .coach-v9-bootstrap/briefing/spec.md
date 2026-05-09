# ATDD Coach — Specification v9

> **Status**: Ready for implementation.
> **Replaces**: `atdd orchestrate`, `atdd babysit`. Valuable machinery from both is absorbed (not deprecated-and-lost) per §0.2.
> **Audience**: Implementer of the `afokapu/atdd` toolkit.
> **Companion**: `atdd-repo-substrate-spec-v12.md` (already shipped). Coach consumes the substrate's repo registry transparently via `bind_rule()`. Implementation issues in `atdd-coach-issues-v3.md`.

---

## 0. Existing toolkit substrate (what coach v9 builds on)

This spec is grounded in machinery that already exists in `afokapu/atdd`. Coach v7 does not reinvent any of it.

### 0.1 Substrate that coach v9 consumes (already shipped)

- **Rule registry** — `bind_rule()`, `Violation`, `RuleMetadata`, `disposition_gate.assert_disposition_satisfied()`, `suppression_scanner` (toolkit conventions + 145 validators).
- **Repo rule substrate (v12)** — WMBT-acceptance, train-acceptance, and security-derived rules in the `repo.*` archetype. Strict by construction, walker-set disposition, phase-driven dispatch via `identity.phase`. See `atdd-repo-substrate-spec-v12.md`.
- **Substrate enforcement convention** — `src/atdd/tester/conventions/acceptance-violation.convention.yaml` with five rules (`acceptance-must-be-measurable`, `acceptance-must-declare-phase`, `disposition-must-not-be-declared`, `validator-binding-must-be-bidirectional`, `metric-implementation-must-exist`). Coach treats these as ordinary toolkit conventions at the PLANNED phase.
- **Substrate runners** — `test_metric_runner::test_metric_threshold_satisfied` (registry-iterating, 1:N), `test_security_ref_binding::test_acceptance_ref_resolves_and_passes` (registry-iterating, 1:N), substrate pytest plugin (1:N harness via `TESTED_BY` edges).
- **Spawn-harness block renderers** — `src/atdd/coach/commands/spawn_harness_blocks.py::render_security_rules_block` already implements substrate §8.2's security_rules block. Coach v7 calls it; `wmbt_rules` and `train_rules` renderers complete the trio (per §7.1).
- **URN graph + resolvers** — `WagonResolver`, `FeatureResolver`, `WMBTResolver`, `AcceptanceResolver`, `TrainResolver`, `TestResolver`, `SecurityResolver`. Available via `atdd repo` (formerly `atdd urn`).
- **Multiplexer abstraction** — `src/atdd/coach/utils/multiplexer.py` with cmux, zellij, tmux backends.
- **Session naming** — `compute_canonical_name`, `is_canonical_name`, `target_grid_label` from `session_naming.py` (issue #470). Rule-IDed as `coach.orchestration.canonical-session-name` and `coach.orchestration.layout-conformance`.
- **Orchestration convention** — `src/atdd/coach/conventions/orchestration.convention.yaml` (444 lines, 14+ rules) encoding worktree-per-issue, wave ordering, dependency wait, micro-commit, stop-before-refactor, worker-checkpoint, token-alert, canonical naming, layout conformance, bash auto-approve patterns. Coach inherits all of this as policy.

### 0.2 What `atdd orchestrate` and `atdd babysit` do today (and what coach absorbs)

`atdd orchestrate` (351 lines, `commands/orchestrate.py`) implements:

- Issue plan building (`build_plan`, `compute_waves`) — fetches GitHub issues, parses dependencies, topologically sorts. **Absorbed** by coach state machine (§4.3); `compute_waves` reused as-is.
- Two-phase commit (Phase A: worktrees, rollback on failure; Phase B: launch, state file `.atdd/orchestrate-state.json` for `--resume`). **Absorbed** by coach with the rollback discipline preserved (§4.6); state file replaced by `decisions.jsonl`.
- Multiplexer-mode dispatch (`workspace` vs `pane`). **Absorbed** by `atdd spawn` (§5.2), which inherits the same flag.
- Canonical naming + layout pass at dispatch time (`apply_canonical_name_and_layout`). **Absorbed** by `atdd spawn` so naming is applied at launch (§7.1.5) and re-applied on drift by an observer rule (§8.3 rule 13).
- Launch-script generation (`render(context)` from `session_template.py` writing `.launch_prompt.txt`). **Absorbed** by `atdd spawn` whose harness extends this template with rule-ID-aware blocks (§7.1).

`atdd babysit` (1043 lines, `commands/babysit.py`) implements:

- Token-count alerting (`load_token_alert_threshold`, `read_token_count`, `check_token_threshold`; default 400k). **Absorbed** as observer rule `06-token-threshold` (§8.3); config under `coach.token_alert_threshold` preserved.
- Bash-pattern auto-approval (`BashPattern`, `_load_bash_patterns`, `classify_prompt`). Patterns live in `orchestration.convention.yaml::babysit.bash_auto_approve_patterns.rules` and `bash_deny_patterns.rules`, already rule-IDed. **Absorbed** as observer rule `13-bash-auto-approve` (§8.3); patterns file unchanged.
- Aggregate approval workflow (`aggregate_approve`) — batch-approve known-safe prompts. **Absorbed** as `atdd observer aggregate-approve` (§5.4).
- Naming + layout drift correction (`correct_naming_drift`, `correct_layout_drift`). **Absorbed** as observer rule `14-canonical-naming-drift` and `15-layout-drift` (§8.3); reuses `coach.orchestration.canonical-session-name` and `coach.orchestration.layout-conformance` rule-IDs.
- Violation detection (`detect_violation` — `.atdd/` hand-edit, SMOKE skip). **Absorbed** as observer rules `04-out-of-scope-edit` and `16-smoke-skip` (§8.3). The "fixed handful of patterns" model is replaced by extensible observer rules; existing detections become two of many.
- Workspace state polling (`process_workspace`, `_screen_hash`). **Replaced** by event-driven runtime watcher (§4.4) and observer sidecars (§8). The polling pattern is what coach was designed to obsolete; nothing to absorb.
- Phase cache via GitHub labels (`_fetch_phase_cache`, `_phase_from_labels`). **Replaced** by coach state-machine ownership of phase. Labels remain a human-visible mirror but are not the source of truth.
- Dashboard rendering (`_render_dashboard`, `SurfaceRow`). **Absorbed** as `atdd observer status` (§5.4) at parity with current functionality; richer dashboard is §12.4 future work.

`atdd orchestrate` and `atdd babysit` are removed from the CLI surface in v7 (no `*-legacy` shim). Their absorbed machinery lives where coach uses it; their decommissioned machinery is documented in §11.

---

## 1. Motivation

Same as v5. `atdd orchestrate` + `atdd babysit` have three structural limits:

1. **Polling-based observation.** Lossy on transitions, slow, fragile.
2. **Coach is "the user".** No durable orchestrator owns the lifecycle.
3. **Trust-based protocol.** `detect_violation` catches a fixed handful of patterns.

`atdd coach` replaces both with an event-driven, durable, observer-augmented orchestrator that **drives** the lifecycle. v7 amplifies the rule-ID payoff: deterministic feedback loops where rules exist, LLM judgment where they don't.

---

## 2. Architectural principles

**Event-driven, not polling.**
**Two-layer separation.** Ephemeral state in `.atdd/runtime/`, durable artifacts in git.
**LLM-agnostic at the orchestration layer.**
**Detect-and-correct, not trust.** Per-agent observer sidecars.
**Two-tier verification.** Tier 1 = existing rule-ID-bound validator substrate (deterministic, fast, suppression-aware). Tier 2 = LLM reviewer at phase boundaries (semantic, slower, references rule-IDs when applicable). (§6.4)
**Adversarial review** at every meaningful phase boundary, plus pre-coach review of issue inputs.
**Rule-ID first.** Every machine-emittable finding carries a canonical rule-ID resolvable via `bind_rule()`. Severity, disposition, fix-hint flow from the registry, not from per-emission magic numbers.
**Phase-driven dispatch via `identity.phase`.** Each repo rule (per substrate v12) declares its phase explicitly. Coach reads `RuleMetadata.phase` per rule and dispatches accordingly. Source kind (toolkit convention vs WMBT-acceptance vs train-acceptance vs security-derived) informs scoping; `identity.phase` is canonical for applicability. Toolkit conventions retain their existing per-archetype scoping.
**Repo contract rules unsuppressible.** Per substrate v12 §2, repo rules are strict-by-construction; suppression markers are ineffective on them. Coach surfaces a stale-suppression observer rule but only for toolkit conventions where `suppress-and-clean` is meaningful.
**Suppression markers honored** for toolkit conventions. `# atdd:suppress(<id>) [UNTIL=...]` is the durable debt-tracking primitive; coach respects it for `suppress-and-clean` toolkit rules and surfaces stale markers separately.
**Coach state is durable.** Append-only `decisions.jsonl`, `judgments.jsonl`, `validations/<sha>/`.
**Mechanical floor + probabilistic ceiling.** Hard enforcement on critical boundaries; soft enforcement on protocol surface.
**PR-based integration.** Compatible with main-branch protection.
**Existing machinery absorbed, not duplicated.** Coach v7 calls `compute_waves`, `render`, `apply_canonical_name_and_layout`, `correct_naming_drift`, `correct_layout_drift`, `aggregate_approve`, `read_token_count`, `_load_bash_patterns` — these functions ship in `commands/orchestrate.py` and `commands/babysit.py` today and move into coach modules with their behavior preserved (§0.2).

---

## 3. Folder structure

### 3.1 Worktree layout (unchanged)

```
forge/
├── main/                           # protected branch worktree
├── feat-issue-358/
├── feat-issue-343/
└── fix-issue-295/
```

### 3.2 Runtime folder layout

`.atdd/runtime/` lives in the main worktree only. Other worktrees write to `../main/.atdd/runtime/agents/<id>/`.

```
main/.atdd/runtime/                 # gitignored
├── coach/
│   ├── manifest.json
│   ├── heartbeat.json
│   ├── decisions.jsonl
│   ├── judgments.jsonl
│   └── state.json
├── agents/<agent-id>/
│   ├── manifest.json
│   ├── heartbeat.json
│   ├── process_heartbeat.json
│   ├── events.jsonl
│   ├── output.log
│   ├── corrections.jsonl
│   ├── pending_correction.txt
│   ├── questions.jsonl
│   ├── answers/<question-id>.json
│   ├── escalations.jsonl
│   └── reviews/<review-id>.json
├── validations/<commit-sha>/       # tier-1 outputs per commit
│   ├── violations.jsonl            # one Violation per line, JSON-serialized
│   ├── disposition-summary.json    # pass/fail per disposition tier
│   ├── suppressed.jsonl            # absorbed-by-marker violations (audit)
│   ├── stale-suppressions.jsonl    # UNTIL-past markers found in scope
│   └── risk-score.json             # {sum, by_severity, by_archetype}
├── issue-reviews/<issue-N>/
│   ├── pass-1-<llm>.json
│   ├── pass-2-<llm>.json
│   ├── pass-3-<llm>.json
│   └── aggregate.json
└── runs/<run-id>/                  # archived snapshots (optional)
```

### 3.3 Gitignore additions

```
# ATDD coach runtime — ephemeral coordination state.
.atdd/runtime/
```

---

## 4. Coach state machine

### 4.1 Per-issue states

Phase enum unchanged from `VALID_PHASES`:

```
INIT      → spawn planner; await PLANNED commit
PLANNED   → run plan-verify gates + reviewer; on pass → RED
RED       → spawn tester; await commit; run RED-verify + reviewer
GREEN     → spawn coder; await commit; run GREEN-verify + reviewer
SMOKE     → run integration smoke tests + reviewer
REFACTOR  → coder cleanup; run REFACTOR-verify + (optional) reviewer
COMPLETE  → open PR; hand off to merge-cascade
BLOCKED   → blocked on human input
```

### 4.2 Pre-coach precondition: issue review

Coach checks each issue for a recent issue-review aggregate verdict (§6.10). `--require-issue-review` defaults to `warn`; teams promote to `block` when ready.

### 4.3 Multi-issue orchestration

Existing `compute_waves()` from `orchestrate.py`. Wave N+1 transitions out of `INIT` only after wave N reaches `COMPLETE` (or `MERGED` if `--strict-deps`).

### 4.4 Event sources

1. **Runtime watcher** — `inotify`/`fswatch` on `.atdd/runtime/agents/*/`.
2. **Git watcher** — `inotify` on each worktree's `.git/refs/heads/`, plus `gh pr view` polling.
3. **Liveness checker** — timer, every 30s.

### 4.5 Decision durability

Every state transition appended to `decisions.jsonl` *before* the action runs. On `--resume <run-id>`, coach reconstructs state-machine positions from the log. Actions are idempotent.

### 4.6 Two-phase commit (worktrees and launch)

Coach inherits the two-phase discipline from `atdd orchestrate` (today's `commands/orchestrate.py`). Multi-issue runs proceed in two transactional phases:

**Phase A — Worktree creation.** For each issue, create a worktree via `git worktree add`. If any worktree fails, all already-created worktrees roll back via `git worktree remove --force` before coach exits. Errors return early; partial state is never persisted. Coach calls the same `_create_worktree` and `_remove_worktree` helpers from today's `commands/orchestrate.py`.

**Phase B — Session launch.** With all worktrees created, render launch prompts (§7.1), spawn agents via `atdd spawn` (§5.2), and apply canonical naming + layout (§7.1.5). Each successful launch writes a decision to `decisions.jsonl`; failed launches log without rolling back already-launched siblings (the assumption: a successfully-launched agent is recoverable on `--resume`, so we don't undo it).

This replaces today's `.atdd/orchestrate-state.json` with `decisions.jsonl` as the durable resume-source. The behavior is identical: `--resume` reconstructs which worktrees exist and which sessions launched, skipping idempotent steps. The state-file format changes (JSON-lines instead of single-document JSON), but the rollback discipline is preserved verbatim.

### 4.7 PR-based COMPLETE

On reaching `COMPLETE`:

1. `gh pr create --base main --head <branch> ...`
2. PR body includes risk score + violation summary (linked to `validations/<sha>/`).
3. Optionally invoke `atdd merge-cascade <pr-number> --auto`.
4. Observe `auto-phase` close → mark `MERGED`.

---

## 5. CLI surface

### 5.1 `atdd coach <issue-numbers...>`

```
atdd coach <issue-numbers...> \
  [--max-retries N]
  [--escalation-channel <path|slack-webhook|github-issue>]
  [--multiplexer cmux|zellij|tmux]
  [--multiplexer-mode workspace|pane]
  [--auto-merge]
  [--strict-deps]
  [--llm <id>]
  [--persona-llm tester=claude-code,coder=codex,reviewer=gpt-5]
  [--judge-llm <id>]
  [--require-issue-review warn|block|auto]
  [--review-phases planned,red,green,smoke,refactor]
  [--skip-review]                            # disables ALL reviewer
  [--risk-threshold-block N]                 # block COMPLETE if risk > N (default: phase-derived)
  [--allow-stale-suppressions]               # default: stale suppressions block COMPLETE
  [--resume <run-id>]
  [--dry-run]
```

### 5.2 `atdd spawn`

```
atdd spawn \
  --persona <planner|tester|coder|reviewer> \
  --llm <claude-code|codex|gemini|glm|...> \
  --worktree <path> \
  --issue <number> \
  --agent-id <unique-id> \
  --runtime <path-to-.atdd/runtime>
  [--phase <RED|GREEN|SMOKE|REFACTOR>]
  [--target-commit <sha>]
  [--prior-attempt <path>]
  [--multiplexer-ref <existing-workspace-or-surface>]
```

### 5.3 `atdd agent <subcommand>`

```bash
atdd agent heartbeat [--current-step "..."]
atdd agent event <type> [--data '...']
atdd agent commit --phase <RED|GREEN|SMOKE|REFACTOR> --message "..." [--wmbt-urn <urn>]
atdd agent ask --question "..." --type <choice|text|approval|confirmation> ...
atdd agent escalate --reason "..." [--severity info|warn|block]
atdd agent done [--summary "..."]
atdd agent context

# reviewer-only:
atdd agent review --target-commit <sha> --report-file <path>
```

### 5.4 `atdd observer <subcommand>`

```bash
atdd observer run --agent-id <id> [--rules-dir <path>]
atdd observer attach --agent-id <id>
atdd observer status                                    # absorbed dashboard from babysit
atdd observer aggregate-approve [--scope <ids>]         # absorbed batch-approval from babysit
```

`atdd observer status` renders the surface dashboard at parity with today's `babysit` dashboard (`SurfaceRow`, `_render_dashboard`, `_format_hms`). Richer dashboard is §12.4 future work.

`atdd observer aggregate-approve` calls today's `aggregate_approve` function — batch-approve known-safe prompts across workspaces with one operator action. Useful when several agents simultaneously hit a tool-prompt that's covered by `babysit.bash_auto_approve_patterns` but blocked by an outer permission scope.

### 5.5 `atdd judge`

```
atdd judge --prompt-template <yaml-path> --schema <json-schema-path> \
           --inputs key1=val1 key2=@file2 [--llm <id>]
```

### 5.6 `atdd issue review <N>`

```
atdd issue review <issue-number> \
  [--passes 3]
  [--llms claude-haiku,gpt-5-mini,gemini-flash]
  [--dimensions systemic,ambiguities,gap,regression,comprehensiveness]
  [--show]
  [--force]
```

### 5.7 `atdd rules <subcommand>`

Discovery commands over the rule registry. Useful for humans during escalation, for agents needing context, for debugging.

```bash
atdd rules show <rule-id>
  # Resolves rule-id (canonical or alias) via bind_rule(); prints
  # severity, description, disposition, validator, fix_hint, recipe,
  # introduced_in, source convention path.

atdd rules where <rule-id>
  # Prints the validator module::function that emits the rule
  # (and the import path inferred from the archetype).

atdd rules grep <pattern>
  # Searches descriptions/IDs/aliases for the pattern.

atdd rules disposition <strict|suppress-and-clean|advisory|documentation-only>
  # Lists every rule with the given disposition.

atdd rules archetype <coder|coach|tester|planner>
  # Lists every rule under the archetype.

atdd rules suppressions [--stale-only] [--rule <id>]
  # Lists active suppression markers (delegates to suppression_scanner).
```

These wrap existing utilities (`bind_rule`, `find_suppressions`, `find_stale_suppressions`) — thin CLI surface.

### 5.8 Mapping to existing commands

| New | Replaces / integrates with |
|------|----------------------------|
| `atdd coach` | `atdd orchestrate` + `atdd babysit` (both removed; valuable machinery absorbed per §0.2) |
| `atdd spawn` | `session_template.py::render` + multiplexer launch + `apply_canonical_name_and_layout` |
| `atdd agent commit` | `git commit` with trailers; hook-validated |
| `atdd agent` (heartbeat/event/...) | new |
| `atdd agent review` | new (reviewer persona) |
| `atdd observer` | absorbs `babysit` (token alerts, bash auto-approve, naming/layout drift, dashboard, aggregate-approve); replaces polling with event-driven runtime watcher |
| `atdd judge` | new |
| `atdd issue review` | new — pre-coach issue meta-review |
| `atdd rules` | new — discovery commands over `bind_rule`/suppression scanner |
| `atdd repo` | already shipped (substrate v12) — graph queries, validation, repo-rule discovery |
| `.atdd/hooks/pre-commit` (extended) | adds trailer enforcement to existing checks |
| (existing) `Violation` + `bind_rule` + `disposition_gate` | tier-1 validator substrate consumed by coach (§6.4) |
| (existing) `RuleMetadata.phase` | canonical for phase dispatch (§6.5) per substrate v12 |
| (existing) `suppression_scanner` | used by coach (§6.6) for toolkit conventions; repo rules unsuppressible |
| (existing) `compute_waves` from `commands/orchestrate.py` | absorbed verbatim into coach state machine (§4.3) |
| (existing) `spawn_harness_blocks.py::render_security_rules_block` | called by `atdd spawn` (§7.1) for substrate §8.2's security_rules block |
| (existing) `multiplexer.py` | unchanged; `atdd spawn` uses it |
| (existing) `session_naming.py` | unchanged; `atdd spawn` calls `compute_canonical_name`, observer rules call `is_canonical_name` |
| (existing) `orchestration.convention.yaml` | unchanged; coach + observer rules read from it |
| (existing) `atdd checkpoint` | called by `atdd agent commit` |
| (existing) `atdd merge-cascade` | invoked on `COMPLETE` if `--auto-merge` |
| (existing) `atdd auto-phase` | observed to detect MERGED |

---

## 6. Coach state machine details

### 6.1 Activities and idempotency

| Action | Idempotent because |
|--------|-------------------|
| Create worktree | `git worktree add` no-op if exists |
| Spawn agent | Checks `.atdd/runtime/agents/<persona>-<issue>-*` for existing live agent |
| Run tier-1 validators | Pure function over commit SHA; results cached in `validations/<sha>/` |
| Run tier-2 reviewer | Checks `agents/reviewer-<issue>-*/reviews/` for existing review on same target_commit + phase |
| Open PR | `gh pr view <branch>` checked first; reuses existing PR |
| Invoke merge-cascade | Idempotent on PR number |

### 6.2 Verification model: two tiers

**Tier 1 — rule-ID-bound deterministic validators (existing substrate).** Coach selects validators per phase + WMBT scope (see §6.5 for selection logic), runs them in parallel against the worktree at the target commit, and consumes the resulting `Violation` records. The `disposition_gate.assert_disposition_satisfied()` function decides pass/fail per validator; coach aggregates across validators.

This tier is fast, deterministic, suppression-aware, and produces structured output the agent and reviewer can both consume.

**Tier 2 — LLM reviewer at phase boundary.** Spawned by coach when tier-1 passes (or all tier-1 fails are absorbed by suppression markers). Runs the persona-specific reviewer prompt (§6.3) and emits a structured report. Reviewer findings reference rule-IDs when applicable; otherwise tagged `rule_id: null` (LLM-only finding).

Both tiers feed coach's routing decision. Tier-1 fails block phase transition mechanically (per disposition). Tier-2 fails block via routing logic in §6.3.

### 6.3 Per-phase adversarial review

Reviewer runs at the exit of each enabled phase. Default enables: PLANNED, RED, GREEN, SMOKE. Optional: REFACTOR. Skip: INIT.

**Per-phase review focus** (rendered into the persona prompt):

| Phase | Reviewer asks |
|-------|---------------|
| `PLANNED` | Do the WMBT cards actually decompose this issue? Are acceptances specific and testable? Are dependencies correct? |
| `RED` | Does each test actually exercise the WMBT contract, or pass trivially? All declared acceptances covered? Tests fail for the *right* reason? |
| `GREEN` | Does each AC have a passing test that genuinely proves the AC? Implementation addresses the WMBT? Diff scope confined to declared targets? |
| `SMOKE` | Is the smoke test actually exercising real infrastructure? Flakiness sources controlled? |
| `REFACTOR` | Did cleanup preserve semantics? Regression risk? Architectural concerns? |

**Hard rules for reviewer (all phases):**

- Different LLM from the agent under review by default. `coach.persona_llm.reviewer ≠ coach.persona_llm.<phase-agent>`.
- **No write permission to the worktree.** Spawn adapter strips commit/edit tools; system prompt forbids edits; observer rule `08-reviewer-edit-attempt` catches violations.
- Only output channel: `atdd agent review --target-commit <sha> --report-file <path>`.
- **Rule-ID resolution.** Reviewer prompt instructs: "When you find a violation that matches a known rule, identify the canonical `rule_id` from the convention files (referenced in the bundled context). Use `atdd rules grep <pattern>` if needed. Otherwise emit `rule_id: null` and provide a clear free-text description."

**Review surfaces.** Every finding tagged with at least one surface:

- `convention` — ATDD convention violation. Most should be rule-ID-bound.
- `task` — issue/WMBT acceptance not addressed.
- `semantic` — wrong logic, test doesn't exercise contract. Often `rule_id: null`.
- `architecture` — layering, coupling, testability. Sometimes rule-ID-bound (boundaries.convention).

**Coach routing on review verdict:**

- `pass` → next state.
- `fail` → respawn with reviewer findings + rule-IDs + fix_hints embedded in feedback.
- `concern` → judge call site #2 (§6.9) decides *block* vs *annotate-and-continue*.

### 6.4 Real-time tier-1 validator dispatch

When the git watcher detects a new commit on a worktree:

1. Parse commit trailers; extract `Phase`, `WMBT-Urn`, `Agent-Id`.
2. **Resolve validator set** per (phase, WMBT scope) — see §6.5.
3. **Run validators in parallel.** Each validator is a pytest module under `src/atdd/<archetype>/validators/`; coach invokes them via `pytest --collect-only` to enumerate, then runs each as a subprocess scoped to the worktree.
4. **Collect `Violation` records.** Validators emit them via `assert_disposition_satisfied()`; coach intercepts via a custom pytest plugin (`coach.runtime.violation_collector`) that writes to `validations/<sha>/violations.jsonl`.
5. **Apply suppression scanner.** Run `find_suppressions()` over the worktree; for each violation, check if its `(rule_id, location)` is suppressed. Suppressed violations move to `suppressed.jsonl`; remaining violations are the active set.
6. **Aggregate by disposition.** Coach groups active violations by disposition:
   - `strict` violations → block (no exceptions).
   - `suppress-and-clean` violations not absorbed by markers → block.
   - `advisory` violations → log, never block.
   - `documentation-only` rules → not enforced (no validator runs).
7. **Compute risk score** (§6.8) and write `risk-score.json`.
8. **Write event** to `events.jsonl` for the agent: `{type: "validation_complete", sha: "...", summary: ...}`.
9. **Coach evaluates per-phase policy** and routes accordingly.

Validator dispatch is configurable via `.atdd/validators/<phase>/` overrides (project-specific) layered over the default selection rules in §6.5.

**Grace window.** After the first commit on a fresh phase, coach waits `coach.validators.grace_window_seconds` (default 30s) before evaluating, allowing the agent to push corrective follow-up commits in flight without churning routing.

### 6.5 Validator selection per phase

Selection is a union of two sources, both resolved per coach phase:

**Toolkit conventions** (existing): per-archetype validators per phase. Default mapping (overrideable via `.atdd/coach/config.yaml::coach.validators.selection`):

| Phase | Toolkit validator set |
|-------|----------------------|
| `PLANNED` | `atdd.planner.validators.*` (acceptance, criteria, wmbt) + `atdd.tester.validators.acceptance-violation.*` (substrate enforcement: measurability, phase-declared, no-disposition, validator-binding, metric-implementation, security-ref-resolved) |
| `RED` | `atdd.tester.validators.*` (red, filename, security) + `coach.rule-id-uniqueness` |
| `GREEN` | `atdd.coder.validators.*` (dead-code, dto, error-response, frontend, presentation) + structural conventions (boundaries, design) |
| `SMOKE` | `atdd.tester.validators.smoke.*` + integration smoke harness from `validators/fixtures/` |
| `REFACTOR` | All `atdd.coder.validators.*` with `disposition: strict` + architecture-lint-only sweep |

**Repo rules** (substrate v12): every `repo.*` rule whose `RuleMetadata.phase` matches the current coach phase, regardless of source kind (WMBT-acceptance, train-acceptance, security). Coach reads `bind_rule(rule_id).phase` per rule.

So a coach phase running `GREEN` selects every repo rule with `phase: GREEN` — typically WMBT acceptances at GREEN, but also any train acceptance authored as `phase: GREEN` (rare but possible), or any security rule whose `bound_acceptance_urn` resolves to an acceptance at GREEN.

The `REFACTOR` phase additionally sweeps every strict-disposition rule from both registries (toolkit and repo), as a regression check before COMPLETE.

**Risk-routing.** A validator marked `disposition: advisory` (toolkit conventions only) always runs but never blocks. `disposition: strict` blocks. `suppress-and-clean` (toolkit conventions only) emits violations but suppressions absorb them — coach sees absorbed and active subsets separately and routes only on active. Repo rules are uniformly `strict` and unsuppressible per substrate v12 §2.

**Per-rule disposition** (declared in convention for toolkit, set by walker to `strict` for repo) wins over per-validator. A single validator can emit violations for multiple rules with different dispositions; the gate evaluates each rule independently.

**RED phase semantics.** An acceptance authored `phase: GREEN` should *fail* at RED (the test exists, the implementation doesn't yet). Per substrate v12 §8.1, the substrate emits `Violation` records based on outcome regardless of phase; coach interprets violations at RED as expected and at GREEN as not. This is coach's concern — not the substrate's. Applies uniformly across harness, metric, and security modes.

### 6.6 Suppression markers honored end-to-end (toolkit conventions only)

For toolkit conventions whose disposition is `suppress-and-clean`, coach uses `suppression_scanner.find_suppressions()` and `is_suppressed()` to:

- **Absorb pre-existing technical debt.** A `suppress-and-clean` violation whose offending line carries `# atdd:suppress(<rule_id>) [UNTIL=YYYY-MM-DD]` is moved to `suppressed.jsonl` and does not block the phase.
- **Surface stale suppressions.** `find_stale_suppressions()` returns markers whose `UNTIL` is past. These go to `stale-suppressions.jsonl`. By default `--allow-stale-suppressions=false` blocks `COMPLETE` if any stale marker exists in the diff scope of the current PR. Observer rule `10-stale-suppression-detected` (§8.3) nudges the agent to address them.
- **Validate marker grammar.** Markers that don't parse, or reference unknown rule-IDs (per `bind_rule`), are surfaced as warnings — agent should correct.

**Repo rules are unsuppressible** (substrate v12 §2). The substrate's walker sets `disposition: strict` for every repo rule, and `disposition_gate.assert_disposition_satisfied()` appends failures unconditionally for strict — without consulting the suppression scanner. Markers like `# atdd:suppress(repo.foo.D003-acc-unit-001)` are silently ignored. Tightening or relaxing a contract happens by editing the WMBT/train/feature YAML, with the graph chain (code, test) updating accordingly.

This means the suppression scanner runs on every commit (existing toolkit machinery) but the suppressed pool for repo rules is always empty. Coach does not special-case this — it routes per disposition and the strict/unsuppressible behavior emerges from the gate's existing logic.

### 6.7 Legacy alias resolution in feedback

When a violation's `rule_id` is a legacy flat-grammar ID (`GREEN-URN-001`, `DEAD-CODE-REACHABILITY-001`, etc.), coach uses `get_canonical_id()` to resolve to the namespaced canonical form before embedding in feedback templates. The agent sees both:

```
[coder.dead-code.reachability sev=2 strict]   (was: DEAD-CODE-REACHABILITY-001)
src/foo.py:12 — Python source files must be reachable from a known entrypoint
→ recipe:adapter#step-1
```

This way the agent learns canonical names while still understanding legacy callsites.

When the canonical ID has migrated (`superseded_by:` set on the rule it bound to), judge call site #6 (§6.9) consolidates the renaming guidance.

### 6.8 Risk score per phase exit

For each commit's tier-1 outputs, coach computes:

```python
risk_score = sum(v.severity for v in active_violations)  # active = not suppressed
risk_breakdown = {
    "by_severity": {1: ..., 2: ..., 3: ..., 4: ..., 5: ...},
    "by_archetype": {"coder": ..., "tester": ..., "planner": ..., "coach": ..., "repo": ...},
    "by_disposition": {"strict": ..., "suppress-and-clean": ..., "advisory": ...},
    "stale_suppressions": ...
}
```

The `repo` slice (substrate v12) sums severity across active repo-archetype violations (WMBT-acceptance, train-acceptance, security-derived). Severity for repo acceptance rules is constant 4; for security rules it's mapped from `abuse_case.severity` (low→2, medium→3, high→4, critical→5). The slice lets PR reviewers see at a glance whether a PR's debt is in toolkit conventions or in failing repo contracts.

Written to `validations/<sha>/risk-score.json`. Surfaced in:

- **Coach routing.** `--risk-threshold-block N` blocks `COMPLETE` if score > N. Defaults: `PLANNED=∞`, `RED=∞`, `GREEN=10`, `SMOKE=15`, `REFACTOR=5` (configurable per phase). The `∞` defaults reflect that early phases legitimately produce code that other phases will validate.
- **Judge inputs.** Risk score is part of every `atdd judge` call's context — judge can weigh it.
- **PR description.** The PR opened on `COMPLETE` includes the score and a link to `validations/<sha>/`.
- **Reviewer prompt.** Reviewer sees the tier-1 risk score and can prioritize accordingly.

### 6.9 Coach judgment via `atdd judge`

Coach is deterministic Python for the structural skeleton. For genuinely ambiguous decisions, calls `atdd judge` with structured context.

**Six v1 call sites** (expanded from v5):

1. **Borderline tier-1 result.** Mixed pass/fail with ambiguous severity, or `suppress-and-clean` rules with new violations clustered around recently-edited lines (might be migration in flight). Response: `{decision: "pass|respawn|annotate", confidence: 0..1, rationale: "..."}`.
2. **Reviewer concern verdict.** Block vs annotate-and-continue. Response: `{decision: "block|annotate_and_continue", rationale: "...", pr_annotation: "..."}`.
3. **Retry-vs-escalate at threshold.** Before consuming final retry: `{decision: "retry|escalate", reasoning: "..."}`.
4. **Cross-phase regression risk.** When tier-1 in a later phase reveals a regression in earlier-phase work: `{decision: "fix_in_place|reopen_prior_phase|escalate"}`.
5. **Issue review aggregate ambiguity.** Mixed pass/concern across issue-review passes: `{decision: "accept|request_revision|escalate", consolidated_feedback: "..."}`.
6. **Superseded rule-ID consolidation** . When a violation references a legacy alias whose canonical rule has `superseded_by` set, judge produces consolidated migration guidance for the spawn-feedback. Response: `{guidance: "...", suggested_aliases: [...]}`.

Every judgment writes to `judgments.jsonl`. Inputs hashed by default; full inputs in gitignored cache.

**Default on judge unavailable.** Conservative fallback (escalate, block, retry). Configurable via `coach.judge.fail_open` (default `false`).

**Discipline for adding new call sites.** The deterministic-first ordering (tier-1 → operator escalation → judge) is load-bearing. New judge call sites require explicit justification on a PR that:

- Demonstrates the ambiguity cannot be resolved by a tier-1 deterministic check (i.e., the ambiguity is genuinely about *what to do*, not *what is the case*).
- Demonstrates that operator escalation isn't the right answer (i.e., the decision is high-frequency enough that escalation would dominate operator attention).
- Specifies the response schema and the `judgments.jsonl` audit-trail expectation.

Without this justification, every ambiguity becomes a judge call and routing logic gradually migrates into prompts — the failure mode this section is designed to prevent. Six call sites is not a target; it's the current count of decisions that have passed this bar.

### 6.10 Pre-coach issue review (`atdd issue review`)

N independent passes (default 3, min 2), each by a different LLM. Each pass evaluates the issue across five dimensions: systemic, ambiguities, gaps, regression risk, comprehensiveness.

When passes flag concerns that map to known rule-IDs (e.g. "this issue conflicts with `coder.boundaries.wagon-isolation`"), the pass output includes the rule-ID; coach surfaces it in the aggregate and posts to the GitHub issue with rule-ID context.

Aggregation logic and judge call site #5 unchanged from v5.

---

## 7. Conventions: prompts, commits, schemas — all YAML

### 7.1 Spawn harness with rule-ID-aware context preload

The spawn adapter pre-bundles context. The harness includes a rule-ID context block:

```yaml
# Section 1 — persona convention file (per-LLM)
include: ${persona_convention_file}            # CLAUDE.md, AGENTS.md, GLM.md, GEMINI.md

# Section 2 — phase + WMBT
phase: GREEN
target_wmbt: wmbt:govern-lifecycle:D003
target_wmbt_full: ${file:plan/govern_lifecycle/D003.yaml}

# Section 3 — issue body
issue_number: 358
issue_body: ${gh_issue_body:358}

# Section 4 — wagon manifest
wagon_manifest: ${file:plan/govern_lifecycle/_govern_lifecycle.yaml}

# Section 5 — phase-relevant conventions (rule-ID-aware)
conventions:
  - path: src/atdd/coder/conventions/dead-code.convention.yaml
    rules_in_scope:                            # subset relevant to this WMBT
      - id: coder.dead-code.reachability
        severity: 2
        disposition: strict
        fix_hint: "Either wire into a composition root, or delete it."
      - id: coder.dead-code.reachability-typescript
        severity: 2
        disposition: strict
        fix_hint: "..."
  - path: src/atdd/coder/conventions/boundaries.convention.yaml
    rules_in_scope: [...]

# Section 5b — repo-derived rules in scope (substrate v12 §8.2)
# Selected by RuleMetadata.phase matching the current coach phase.
wmbt_rules:                                    # WMBT-acceptance rules
  - wmbt_urn: wmbt:govern-lifecycle:D003
    rules:
      - id: repo.govern-lifecycle.D003-acc-unit-001
        acceptance_urn: acc:govern-lifecycle:D003-UNIT-001-token-rotation
        purpose: "Token rotation invalidates the prior session token within 5s"
        expectations:
          - "After rotate(), the prior token returns 401 on subsequent calls"
          - "The new token is returned in the response body, not headers"
        harness_type: unit
        signal_metric: null

train_rules:                                   # train-acceptance rules (typically SMOKE)
  - train_urn: train:checkout-train
    rules:
      - id: repo.checkout-train.acc-idempotent-on-retry
        purpose: "Re-running the flow with the same idempotency key produces no duplicate side effects"
        expectations: [...]

security_rules:                                # security-derived rules
  - feature_urn: feature:auth:session-management
    rules:
      - id: repo.auth.session-management-security-001
        security_urn: security:auth:session-management:001
        threat: "Session Hijacking — Attacker steals session token via XSS"
        mitigation: "HttpOnly cookies, CSP headers"
        severity: 4
        acceptance_ref: acc:auth:D001-SEC-001-session-protection

# Section 6 — runtime context
runtime:
  agent_id: coder-358-7b2c
  worktree: /Users/.../forge/feat-issue-358
  runtime_path: /Users/.../forge/main/.atdd/runtime
  multiplexer_ref: surface:42

# Section 7 — protocol (forbiddens, required CLI)
protocol:
  required_cli: { ... }
  forbidden: [ ... ]
  rule_id_grammar: "<archetype>.<convention_short_name>.<rule_name>"
  bind_rule_contract: |
    Validators MUST call bind_rule("<canonical_id>") at module-import time.
    The named rule MUST exist in a convention's rules: block.
    See SPEC-COACH-RULEID-0007.

# Section 8 (only on respawn) — prior attempt, rule-ID-rich
prior_attempt:
  commit_sha: abc123
  active_violations:
    - rule_id: coder.dead-code.reachability
      severity: 2
      disposition: strict
      location: src/foo.py:12
      detail: "src.foo.helper is unreachable from any graph root"
      fix_hint: "Either wire into a composition root, or delete it."
      fix_hint_ref: "recipe:adapter#step-1"
      legacy_alias: DEAD-CODE-REACHABILITY-001     # if applicable
    - rule_id: null                                # LLM-only finding
      severity: 3
      surface: semantic
      detail: "test doesn't actually exercise the contract"
  reviewer_findings: [...]                          # same shape
  guidance: |
    Address each violation. Strict-disposition violations must be fixed.
    Suppress-and-clean violations may be marked with `# atdd:suppress(...)`
    only if accompanied by a tracking-issue link in commit message.
```

The `rules_in_scope` selection is computed per (phase, WMBT.targets, archetype). Coach reads the WMBT's declared targets, walks them through `bind_rule`'s registry, and includes only relevant rules. Keeps the prompt tight while still giving the agent everything it needs.

The `wmbt_rules:`, `train_rules:`, `security_rules:` blocks are rendered by `src/atdd/coach/commands/spawn_harness_blocks.py`. The `render_security_rules_block` function ships today (issue #422); `render_wmbt_rules_block` and `render_train_rules_block` are coach v9 deliverables (track-T issues, §11). All three follow the same field-mapping pattern documented in `spawn_harness_blocks.py`.

**Per-LLM convention files extended** in v7 to include the rule-ID grammar and `bind_rule` contract:

| LLM | Convention file |
|-----|-----------------|
| claude-code | `CLAUDE.md` (extended with rule-ID grammar section) |
| codex | `AGENTS.md` |
| gemini | `GEMINI.md` (or `AGENTS.md`) |
| glm | `GLM.md` (or `AGENTS.md`) |

`atdd sync` regenerates these files from `src/atdd/coach/templates/` and the rule-ID convention.

### 7.1.5 Canonical naming and layout pass at spawn (absorbed from orchestrate)

Right after launching a session, `atdd spawn` calls `apply_canonical_name_and_layout` (today in `commands/orchestrate.py`) to:

1. Compute the canonical session name via `compute_canonical_name(repo_short, issue_number, slug)` per the `coach.orchestration.canonical-session-name` rule.
2. Rename the multiplexer surface (e.g. `cmux rename-tab`).
3. Send `/rename <canonical_name>\n` into the running agent so the in-conversation header matches.
4. Print the target grid layout via `target_grid_label(surface_count)`.

The function is best-effort: rename failures don't crash the spawn flow because the observer rule `14-canonical-naming-drift` (§8.3) re-applies on subsequent ticks. This preserves today's behavior verbatim — the helper moves into a coach module with no functional change.

### 7.2 Persona prompt templates

`src/atdd/coach/prompts/persona/<persona>.prompt.yaml`. Per-phase reviewer prompts at `prompts/persona/reviewer/<phase>.prompt.yaml`.

Reviewer template includes a rule-resolution block:

```yaml
rule_id_resolution: |
  When emitting a finding, identify the canonical rule_id when one applies:

  1. Check the bundled `conventions[].rules_in_scope` block for IDs whose
     description matches the violation.
  2. If multiple candidates match, prefer the most specific (lowest scope).
  3. If no candidate matches, emit the finding with `rule_id: null` and
     a clear free-text description.

  Severity is derived from the rule when rule_id is non-null. For null
  rule_id, you assign severity (1..5) per the SPEC-COACH-RULEID-0003 scale.

  Aliases: if you only know a legacy ID like GREEN-URN-001, include it under
  `legacy_alias` and coach will resolve to canonical form.
```

### 7.3 Commit trailers — mechanically enforced

Same as v5. Pre-commit hook validates `Agent-Id`, `Issue`, `WMBT-Urn`, `Phase` trailers. WMBT URN format `^wmbt:[a-z][a-z0-9-]+:[A-Z][0-9]+$`. `prepare-commit-msg` auto-injects.

### 7.4 Review report schema (rule-ID-first)

`src/atdd/coach/schemas/review-report.schema.json`:

```json
{
  "review_id": "rev-2026-...-358-c1e9",
  "target_commit": "abc123",
  "reviewer_agent_id": "reviewer-358-c1e9",
  "wmbt_urn": "wmbt:govern-lifecycle:D003",
  "phase": "GREEN",
  "verdict": "pass | concern | fail",
  "tier1_risk_score": 7,                       // pulled from validations/<sha>/risk-score.json
  "findings": [
    {
      "rule_id": "coder.dead-code.reachability",   // canonical, resolvable via bind_rule
      "rule_id_legacy_alias": "DEAD-CODE-REACHABILITY-001",   // if reviewer mentioned it
      "severity": 2,                               // derived from registry when rule_id != null
      "disposition": "strict",                     // derived from registry when rule_id != null
      "surface": "convention | task | semantic | architecture",
      "location": "src/foo.py:12",
      "acceptance_ref": "AC-UNIT-001",
      "description": "...",
      "evidence": "..."
    },
    {
      "rule_id": null,                             // LLM-only finding
      "severity": 3,                               // reviewer-assigned per 1..5 scale
      "surface": "semantic",
      "location": "tests/test_funnel.py:42",
      "acceptance_ref": null,
      "description": "Test doesn't actually invoke the system under test",
      "evidence": "..."
    }
  ],
  "ac_coverage": {
    "AC-UNIT-001": "covered | not_covered | partial",
    "AC-UNIT-002": "covered | not_covered | partial"
  },
  "summary": "...",
  "recommendations": ["..."]
}
```

**Hard rules:**

- `verdict` cannot be `pass` if any AC is `not_covered` (mechanical defense against false-completion).
- When `rule_id != null`, `severity` and `disposition` MUST match `bind_rule(rule_id)` — schema validator runs this check at coach intake.
- `verdict` cannot be `pass` if any finding has `disposition: strict` AND `rule_id != null`.

### 7.5 Validator output schema (tier-1)

`src/atdd/coach/schemas/validator-result.schema.json` — already largely defined by `Violation`:

```json
{
  "rule_id": "coder.dead-code.reachability",     // required, resolves via bind_rule
  "severity": 2,                                  // 1..5 per SPEC-COACH-RULEID-0003
  "location": "src/foo.py:12",                   // path:line[:col]
  "detail": "...",
  "fix_hint_ref": "recipe:adapter#step-1",       // optional, recipe pointer
  "validator_module": "test_dead_code_python",   // for traceability
  "validator_function": "test_no_unreachable_python_files"
}
```

Disposition NOT serialized on the violation (it's a registry property of the rule, not the violation). Coach reads disposition via `bind_rule(rule_id).disposition` at routing time.

### 7.6 Spawn-feedback templates (rule-ID-rich)

When respawning an agent after a failed attempt, the feedback section uses this canonical format per active violation:

```
[<canonical_rule_id> sev=<severity> <disposition>]
<location> — <description>
fix: <fix_hint or "no canonical fix; see recipe">
recipe: <recipe pointer if available>
(legacy alias: <alias> if reviewer/validator mentioned it)
```

Concrete:

```
[coder.dead-code.reachability sev=2 strict]
src/foo.py:12 — Python source files must be reachable from a known entrypoint (composition root, train, test, or registered exception)
fix: Either wire into a composition root, or delete it.
recipe: recipe:adapter#step-1
```

For null-rule findings:

```
[no rule sev=3 surface=semantic]
tests/test_funnel.py:42 — Test doesn't actually invoke the system under test
guidance: Import src.funnel.FunnelStep and assert against its return value.
```

The agent's next attempt sees structured, rule-tagged feedback; the LLM has zero ambiguity about what to fix and how.

### 7.7 Schema inventory

New schemas under `src/atdd/coach/schemas/`:

- `coach-decision.schema.json`
- `coach-judgment.schema.json`
- `agent-event.schema.json`
- `agent-manifest.schema.json`
- `coach-question.schema.json`
- `correction.schema.json`
- `review-report.schema.json`
- `validator-result.schema.json`
- `risk-score.schema.json`
- `issue-review-pass.schema.json`
- `issue-review-aggregate.schema.json`
- `judge-borderline-tier1.response.schema.json`
- `judge-reviewer-concern.response.schema.json`
- `judge-retry-vs-escalate.response.schema.json`
- `judge-regression-scope.response.schema.json`
- `judge-issue-review-aggregate.response.schema.json`
- `judge-superseded-rule-consolidation.response.schema.json`

---

## 8. Observer architecture (detect-and-correct)

Same shape as v5. Adds three new rules tied to the rule-ID system.

### 8.1 What the observer does

Tails `output.log`. Watches worktree. Runs detection rules. On fire: writes correction.

### 8.2 Correction injection paths

1. **CLI return-path** (default).
2. **Multiplexer send-keys** for stuck agents.
3. **Kill and respawn** for catastrophic failures.

### 8.3 Default rules

| Rule | Trigger | Correction | Origin |
|------|---------|-----------|--------|
| `01-unstructured-question` | Question patterns outside `atdd agent ask` | "Reformulate via `atdd agent ask --type ...`." | new |
| `02-token-silence` | No tokens >90s | "You've been silent for {N}s. Are you blocked? Use `atdd agent escalate`." | new |
| `03-completion-claim-without-commit` | "task complete" / "done" without commit | "You indicated completion but no commit was detected." | new |
| `04-out-of-scope-edit` | File outside WMBT target paths | "You modified {path} not in WMBT scope. Revert or escalate." | absorbed (`detect_violation` `.atdd/` clause) |
| `05-missed-heartbeat` | No `heartbeat.json` >M seconds | "Call `atdd agent heartbeat` after each significant action." | new |
| `06-token-threshold` | Context status >threshold | "Approaching context limit. Run `/compact`." | absorbed (`check_token_threshold`, default 400k from `coach.token_alert_threshold`) |
| `07-llm-judge-on-commit` | Commit events; runs `atdd judge` against WMBT | If judge flags issues: structured feedback. | new |
| `08-reviewer-edit-attempt` | Reviewer agent's output mentions edits/commits | "You are a Reviewer. You may not edit or commit." | new |
| `09-validator-failure-ignored` | Tier-1 validator failed on prior commit, agent committed again without addressing | "Prior commit had validator failures. Address before continuing: {fix_hints}." | new |
| `10-stale-suppression-detected` | Agent's commit touches a file with stale `# atdd:suppress(<id>) [UNTIL=<past>]` marker (toolkit conventions only — repo rules are unsuppressible) | "Stale suppression marker for {rule_id} found at {location} (UNTIL={date}, expired). Either fix the underlying violation or extend the deadline." | new |
| `11-unbound-rule-id-in-validator` | Agent (likely tester/coder) creates a validator without `bind_rule()` call | "Validator emitting rule_id={id} must call bind_rule('{canonical_id}') at module-import time. See SPEC-COACH-RULEID-0007." | new |
| `12-rule-id-grammar-violation` | Agent declares a rule with non-canonical-grammar `id` field | "rule_id '{id}' violates SPEC-COACH-RULEID-0001 grammar (`<archetype>.<convention>.<rule>`). Use canonical form; place legacy IDs under aliases." | new |
| `13-bash-auto-approve` | Tool prompt matches a known-safe pattern from `orchestration.convention.yaml::babysit.bash_auto_approve_patterns.rules` | Auto-approve. On match against `bash_deny_patterns.rules`: escalate. | absorbed (`classify_prompt`, `_classify_bash_command`) |
| `14-canonical-naming-drift` | Multiplexer surface name no longer matches canonical (`is_canonical_name` returns False, or differs from cached expected) | Re-apply rename via `correct_naming_drift`. Logs `coach.orchestration.canonical-session-name`. | absorbed (`correct_naming_drift`) |
| `15-layout-drift` | Surface count or arrangement no longer matches `target_grid_label` | Re-apply layout via `correct_layout_drift`. Logs `coach.orchestration.layout-conformance`. | absorbed (`correct_layout_drift`) |
| `16-smoke-skip` | Phase transition from GREEN to REFACTOR without SMOKE | "Transition to REFACTOR detected without passing through SMOKE. SMOKE is required per orchestration convention." | absorbed (`detect_violation` `--status REFACTOR` clause) |
| `17-repo-rule-disposition-declared` | Agent edits a WMBT/train/feature YAML adding a `disposition:` field on an acceptance or abuse_case | "Repo contract rules cannot declare disposition (substrate v12 §4.4). Disposition is set by the walker to strict. Remove the field." | new (substrate v12 alignment) |

Rules `10`, `11`, `12`, `17` are tier-2 bridge rules — they catch protocol-level issues before tier-1 validators flag them, shortening the feedback loop. Rules `13`–`16` carry behavior absorbed from `atdd babysit`; the underlying functions (`classify_prompt`, `correct_naming_drift`, `correct_layout_drift`, `detect_violation`) move from `commands/babysit.py` into observer-rule modules with no functional change.

### 8.4 Activity signal independent of tool calls

Process heartbeat (liveness daemon) + activity heartbeat (output stream growth). Process alive + activity stale → stuck. Both stale → crashed.

### 8.5 Compliance is a budget

With observer + mechanical commit hook + rule-ID-bound tier-1 + tier-2 review + AC coverage check + suppression honoring, residual non-compliance on the soft surface is well under 5%. Defenses stack:

- Pre-commit hook → structural violations.
- Tier-1 validators → convention violations with rule-ID-bound feedback.
- Suppression scanner → debt absorbed and tracked, not silently ignored.
- Observer → protocol violations in real time.
- Tier-2 reviewer → semantic violations, sometimes rule-ID-bound.
- AC coverage check → false-completion mechanically detectable.
- Risk score thresholds → high-debt PRs blocked even if individual violations pass.

---

## 9. Human escalation

Three triggers (unchanged from v5):

1. **Agent escalates** via `atdd agent escalate`.
2. **Coach escalates** when verification fails N times, deadlocks, or judge defers.
3. **Question requires human** when `atdd agent ask --type text` doesn't auto-resolve.

Channels: file (default), Slack/Discord webhook, GitHub issue.

When escalating about a rule-ID-bound violation, the escalation payload includes the rule's metadata via `bind_rule()` so the human sees disposition, recipe, severity context.

---

## 10. Configuration

`.atdd/config.yaml` `coach:` section:

```yaml
coach:
  default_llm: claude-code
  persona_llm:
    planner: claude-code
    tester: claude-code
    coder: claude-code
    reviewer: gpt-5
  judge_llm: claude-haiku
  observer:
    rules_dir: .atdd/observer/rules
    activity_silence_seconds: 90
    process_silence_seconds: 30
  review:
    enabled: true
    phases: [planned, red, green, smoke]
    same_model_warning: true
    same_model_allowed: false
  validators:
    enabled: true
    grace_window_seconds: 30
    selection: default                       # or path to override
    pytest_args: ["-x", "--tb=short"]        # passed to validator subprocesses
  suppressions:
    honor: true                              # apply suppression markers
    block_on_stale: true                     # COMPLETE blocked if stale UNTIL in scope
    grace_days: 7                            # warn N days before UNTIL expires
  risk_thresholds:
    planned: null                            # null = no threshold
    red: null
    green: 10
    smoke: 15
    refactor: 5
    complete: 0                              # PR-ready; no active strict violations
  judge:
    enabled: true
    fail_open: false
    log_full_inputs: false
  issue_review:
    passes: 3
    llms: [claude-haiku, gpt-5-mini, gemini-flash]
    dimensions: [systemic, ambiguities, gap, regression, comprehensiveness]
    require_for_coach: warn
    stale_after_days: 14
  escalation:
    channel: file
    slack_webhook: null
    github_label: coach-escalation
  retries:
    per_state_machine: 3
    per_agent: 2
  token_alert_threshold: 400000

sync:
  agents:
    - claude
    - codex
    - gemini
    - glm
```

---

## 11. Implementation plan

The implementation is split into **7 tracks** dispatched across **6 parallel agents** rather than sequential waves. Tracks are scoped by dependency boundary, not by spec section. The full set of issues with their bodies is in `atdd-coach-issues.md` (companion document); this section references them by number.

### 11.1 Track summary

| Track | Owner | Scope | Issues | Depends on |
|---|---|---|---|---|
| **C0 — Contract freeze** | Agent J1 | Centralized schemas for runtime events, validator results, corrections, decisions, judgments; runtime directory layout contract | #C0 | — |
| J — Coach state machine + agent CLI | Agent J1 | `atdd coach` MVP, `atdd agent` subcommands, decision/judgment durability, two-phase commit, runtime layout | #J1–#J6 | C0 |
| K — Spawn + canonical naming | Agent K1 | `atdd spawn`, harness rendering with substrate blocks (`wmbt_rules`, `train_rules`, `security_rules`), naming + layout pass, **orchestrate parity tests** | #K1–#K5 | C0, J (#J1, #J2) |
| L — Observer + absorbed babysit machinery | Agent L1 | `atdd observer`, runtime watcher, all 17 default observer rules, dashboard, aggregate-approve, **babysit parity tests** | #L1–#L8 | C0, J (#J1, #J2) |
| M — Tier-1 validator dispatch | Agent M1 | Git watcher, validator dispatch via existing pytest substrate, suppression scanner integration, risk score | #M1–#M5 | C0, J (#J1, #J3) |
| N — Reviewer + review schemas | Agent N1 | Reviewer persona, no-write spawn adapter, review-report schema with rule-ID-first fields and AC coverage hard rule, per-phase review integration | #N1–#N5 | C0, K (#K2), M (#M3) |
| O — Judge + issue review | Agent O1 | `atdd judge` core, six call sites, `atdd issue review` multi-pass | #O1–#O5 | C0, J (#J1) |
| P — Discovery, sync, config | Agent P1 | `atdd rules` discovery commands, per-LLM convention file generation, config loader, decommissioning of `atdd orchestrate` and `atdd babysit` from CLI | #P1–#P6 | C0, J (#J1); P5 also gates on K5; P6 also gates on L8 |
| Q — Integration acceptance | (merge-window) | End-to-end coach-driven cycle on a real issue with integration-bug observation | #Q1 | All tracks |

**C0 is the contract freeze that unblocks parallelism.** Six agents working simultaneously need stable schemas for the artifacts they produce and consume. C0 lands before #J1 (or in parallel as a documentation-only PR) and produces the schemas listed in the issue body. After C0 lands, J/K/L/M/N/O/P all start in parallel — there are no schema-shape conflicts because everything was agreed up front.

Tracks J through P run in parallel after C0 and J1. Q is the coach's done-line.

### 11.2 Sequencing within tracks

**Track J** is the foundation. Issues sequence as #J1 (coach state machine MVP) → #J2 (`atdd agent` CLI) → #J3 (decision durability) → #J4 (two-phase commit absorbed from orchestrate) → #J5 (runtime watcher event sources) → #J6 (resume from decisions log).

**Track K** starts after #J1 and #J2. The spawn harness needs the agent CLI in place to render the right runtime context block. #K1 wraps `session_template.py::render`; #K2 adds substrate spawn blocks via `spawn_harness_blocks.py` (extending the existing `render_security_rules_block` with `render_wmbt_rules_block` and `render_train_rules_block`); #K3 adds canonical-naming pass at spawn (absorbed from `apply_canonical_name_and_layout`); #K4 adds per-LLM convention file integration.

**Track L** starts after #J1 and #J2. The observer needs the agent CLI for correction injection and the runtime layout for sidecar files. Issues sequence as #L1 (observer-run skeleton + correction injection paths) → #L2 (basic rules 01–05 + 08–09) → #L3 (rule 06 token threshold absorbed from `check_token_threshold`) → #L4 (rules 13–16 absorbed from babysit's `classify_prompt`, `correct_naming_drift`, `correct_layout_drift`, `detect_violation`) → #L5 (rules 10–12, 17 substrate-aware) → #L6 (`atdd observer status` dashboard absorbed from `_render_dashboard`) → #L7 (`atdd observer aggregate-approve` absorbed from `aggregate_approve`).

**Track M** starts after #J1 and #J3. Issues sequence as #M1 (git watcher + commit trailer parsing) → #M2 (custom pytest plugin `coach.runtime.violation_collector`) → #M3 (validator selection per phase including substrate v12 `RuleMetadata.phase` dispatch) → #M4 (suppression scanner integration, repo-rule strictness pass-through) → #M5 (risk score with `repo` archetype slice).

**Track N** starts after #K2 (spawn supports reviewer persona) and #M3 (validator output is structured). Issues sequence as #N1 (reviewer persona + no-write spawn adapter) → #N2 (review-report schema with AC-coverage hard rule) → #N3 (per-phase reviewer prompts) → #N4 (judge call site #2: reviewer concern verdict) → #N5 (`atdd agent review`).

**Track O** runs in parallel with K, L, M, N after #J1. Issues sequence as #O1 (`atdd judge` core) → #O2 (judge call sites 1, 3, 4) → #O3 (judge call site 5: issue review aggregate) → #O4 (judge call site 6: superseded rule consolidation) → #O5 (`atdd issue review` multi-pass).

**Track P** runs in parallel with everything after #J1. Issues sequence as #P1 (`atdd rules show/where/grep`) → #P2 (`atdd rules disposition/archetype/suppressions`) → #P3 (per-LLM convention file generation) → #P4 (config loader extensions for `coach.*` block) → #P5 (decommission `atdd orchestrate`: remove from CLI registry, archive code, error message points to `atdd coach`) → #P6 (decommission `atdd babysit` similarly).

**Track Q** is the coach's done-line. #Q1 runs an end-to-end coach-driven issue from `atdd coach <N>` through `COMPLETE` with PR opened. Until #Q1 passes, coach is not done.

### 11.3 Decommissioning `atdd orchestrate` and `atdd babysit` (Track P, #P5–#P6)

Decommissioning is gated on **parity test suites** that operationalize the "behavior parity" claim made by absorption issues. Without parity tests, "behavior parity" is a review-time judgment call; with them, parity is a CI-enforced equivalence.

- **#K5 — Orchestrate parity suite.** Fixture-driven tests that run `atdd orchestrate <args>` (preserved old code path) and `atdd coach <equivalent args>` and assert equivalent observable behavior: worktree creation order, multiplexer dispatch, canonical naming application, state file contents (modulo format change from `orchestrate-state.json` to `decisions.jsonl` — content semantically equivalent), session prompt rendering. Lands inside Track K because that's where orchestrate's machinery is absorbed.
- **#L8 — Babysit parity suite.** Same pattern: side-by-side runs of `atdd babysit` and `atdd observer` against fixture multiplexer states, asserting equivalent token-alert firing, bash-pattern auto-approval, naming/layout drift correction, dashboard output. Lands inside Track L because that's where babysit's machinery is absorbed.

When all absorption is complete AND #K5 and #L8 pass on CI:

- #P5 archives `commands/orchestrate.py` to `commands/_archived/`, removes from CLI registry.
- #P6 archives `commands/babysit.py` similarly.
- Invoking `atdd orchestrate <args>` returns: `atdd orchestrate has been removed in coach v9. Use 'atdd coach <issue-numbers>' instead. Migration: every flag maps directly per atdd-coach-spec-v9.md §5.1.`
- Invoking `atdd babysit <args>` returns: `atdd babysit has been removed in coach v9. Use 'atdd observer status' (dashboard), 'atdd observer aggregate-approve' (batch approve), or 'atdd coach' (end-to-end) per atdd-coach-spec-v9.md §0.2.`
- The orchestration convention file (`src/atdd/coach/conventions/orchestration.convention.yaml`) is unchanged — it remains the rule-ID home for all the absorbed rules. Rule-IDs continue to resolve via `bind_rule()`.

No `*-legacy` shim is shipped. The hard cut is intentional: substrate v12 set the precedent (CLI rename `atdd urn` → `atdd repo` was a hard rename); coach v9 follows.

### 11.4 PR review burden

Six agents producing ~42 issues will produce roughly 42–60 PRs (some issues spawn follow-ups). Sustainable review load is roughly one human reviewer per 2–3 active agent PRs. If review bandwidth is constrained, scale down to 3–4 agents and accept slower wall-clock progress to avoid PR queue collapse.

### 11.5 Self-hosting inflection

After #M5 (risk score) and #L4 (absorbed observer rules), coach has enough self-hosting capability to drive its own remaining issues (Tracks N, O, P after their entry points) via `atdd coach`. The team decides whether to dogfood from this point. Substrate v12 at issue #17 (worked example) and coach v9 at #Q1 share this same property — done-line is "the system can now manage its own development."

### 11.6 Integration-bug observation in #Q1

The first end-to-end coach-driven cycle (#Q1) will surface substrate↔coach integration bugs that no individual issue's tests can catch. The substrate is shipped, coach v9 components ship individually with unit tests, but the *integration surface* between them is unproven until #Q1 runs. Acceptance criteria for #Q1 explicitly require:

- Logging every substrate↔coach handoff (validator invocation, registry lookups, spawn-harness block rendering, gate verdict consumption) at INFO level.
- Inventory of any integration bugs discovered during the cycle, filed as follow-up issues against the appropriate track.
- A noted expectation that follow-up "integration hardening" PRs may be needed before coach v9 is considered production-ready beyond the worked example.

This is honesty about the integration risk: the architecture is sound (per the teammate review), but first contact with reality always reveals coordination details that survive the spec.

---

## 12. Future / v3 features

### 12.1 Coach-as-LLM (research)

Same as v5. Defer until ~20 v1 cycles audit `judgments.jsonl` for load-bearing LLM calls.

### 12.2 Replay-based test stability

Cache LLM responses keyed by prompt hash.

### 12.3 Worktree pool

Pre-allocate worktrees.

### 12.4 Observability dashboard

Web UI reading `.atdd/runtime/`. Until then: `git log`, `tail -f decisions.jsonl`, `tail -f judgments.jsonl`, `atdd observer attach`, `atdd rules` discovery.

### 12.5 Cross-machine coach

Optional Postgres backend for multi-workstation teams.

### 12.6 Multi-reviewer ensembles

For high-stakes paths (security-sensitive, declared by rule-ID disposition or by config): spawn multiple reviewers; consensus required.

### 12.7 Rule-ID risk model evolution

The current risk score is `sum(severity)` over active violations. Future: weighted scoring (factor in disposition, archetype, repeat offenders, time-since-last-violation), regression-history-aware (a rule that the agent already broke once this run weights heavier), historical baseline (was this rule clean before this branch?).

### 12.8 Issue review on PRs

Same multi-pass review on PR descriptions before merge.

### 12.9 Rule-ID health metrics

Coach emits per-run aggregate metrics: violations introduced, suppressions added, suppressions cleared, stale suppressions remaining, top-10 violated rules per run. Surface as PR comment or run-summary file. Lets the team see whether the codebase is gaining or losing technical debt run over run.

---

## 13. Out of scope

- Worktree creation primitives (existing).
- Branch protection setup (project's GitHub config).
- Issue creation, WMBT decomposition (`atdd issue`).
- LLM API key management.
- Cross-machine coordination (v3.5).
- New rule-ID grammar or new DOMAIN values (governed by `SPEC-COACH-RULEID-0001..0007`; SPEC edits go through that workstream, not coach).

---

## 14. Glossary

- **Wagon / Feature / WMBT / Train** — see existing ATDD docs.
- **Phase** — `INIT|PLANNED|RED|GREEN|SMOKE|REFACTOR|COMPLETE|BLOCKED`.
- **Coach** — orchestrator process (`atdd coach`).
- **Persona** — agent role (`planner|tester|coder|reviewer`).
- **Tier-1 validator** — existing rule-ID-bound deterministic validator; emits `Violation` records.
- **Tier-2 reviewer** — LLM reviewer at phase boundary.
- **Rule-ID** — namespaced canonical identifier `<archetype>.<convention>.<rule>` per `SPEC-COACH-RULEID-0001`. Resolves via `bind_rule()`.
- **Disposition** — per-rule CI policy: `strict | suppress-and-clean | advisory | documentation-only`.
- **Suppression marker** — inline `# atdd:suppress(<rule_id>) [UNTIL=<date>]` pragma; tracked technical debt.
- **Risk score** — sum of severity over active (non-suppressed) violations at a phase exit.
- **AC coverage** — per-AC status block in review reports; `pass` requires all covered.
- **Issue review** — pre-coach 2–3-pass cross-LLM review of issue body.
- **Decision log** — `decisions.jsonl`. **Judgment log** — `judgments.jsonl`. **Validation snapshot** — `validations/<sha>/`.

---
