# ATDD Coach Decomposition — Source of Truth

| | |
|---|---|
| **Version** | 1.2-train-amended-swept |
| **Status** | RATIFIED — train-native correction applied; sweep complete; ready for execution |
| **Date** | 2026-05-30 |
| **Owner** | Operator (acts as coach); worker agents execute children |
| **Scope** | Decompose `atdd.coach.commands.coach` into train-native layers; preserve all incident-hardened behavior; close issues #840, #871, #872, #882 along the way |
| **Non-goals** | Adopt Temporal or LangGraph as a premise; delete behavior; change the public CLI surface |
| **Replaces** | Ad-hoc orchestration code in `atdd.coach.commands.coach` |
| **Convention markers** | "MUST", "MUST NOT", "SHOULD" used per RFC 2119 |

---

## Table of contents

0. [Document purpose](#0-document-purpose)
1. [Executive summary](#1-executive-summary)
2. [Why we're doing this](#2-why-were-doing-this)
3. [Target architecture](#3-target-architecture)
4. [Typed contracts](#4-typed-contracts)
5. [Runtime data model](#5-runtime-data-model)
6. [End-to-end event flow](#6-end-to-end-event-flow)
7. [Orchestration runners](#7-orchestration-runners)
8. [Observer](#8-observer)
9. [Invariants and incident defenses](#9-invariants-and-incident-defenses)
10. [Test gates](#10-test-gates)
11. [Compatibility and deprecation](#11-compatibility-and-deprecation)
12. [Migration plan](#12-migration-plan)
13. [Sequenced children (10)](#13-sequenced-children-10)
14. [Effort estimate](#14-effort-estimate)
15. [Gradual benefit map](#15-gradual-benefit-map)
16. [Risks and mitigations](#16-risks-and-mitigations)
17. [Glossary](#17-glossary)
18. [Appendix](#18-appendix)
19. [Coach operating manual](#19-coach-operating-manual)
20. [Session handoff protocol](#20-session-handoff-protocol)
21. [Follow-up tasks (out of scope for the migration)](#21-follow-up-tasks-out-of-scope-for-the-migration)

---

## 0. Document purpose

This document is the **single source of truth** for the Coach decomposition. Every child issue body, every PR description, every architectural validator MUST refer to this document and MUST NOT contradict it. If a decision needs to change, **the document is updated first**, then implementation follows. Drift between document and code is treated as a bug.

The operator's role is **coach** (orchestrates, reviews, decides). Worker agents implement every child issue through the standard ATDD lifecycle (`INIT → PLANNED → RED → GREEN → SMOKE → REFACTOR → COMPLETE`). Workers MUST read this document before starting any child.

---

## 1. Executive summary

`atdd.coach.commands.coach` today mixes five distinct responsibilities: ATDD phase policy, stateful train-runner orchestration, runtime execution, agent control, and external integrations. This coupling causes brittle screen-scraping (#840), shim gaps (#871, #872), broken Project v2 board sync (#882), and tests that have to mock half the world.

We decompose Coach into **ATDD-native train layers** with strict, validator-enforced dependency rules. **Coach-core becomes pure policy** (no I/O, no subprocess, no `gh`, no cmux, no threading) — importable as a library, table-testable in milliseconds. State, execution, integration, and agent IO live in separate layers behind typed contracts. The CLI surface is unchanged.

A `TrainRunner` protocol is defined now; **the JSONL-backed train runner ships as the first and only implementation**. Temporal and LangGraph are reserved as future backends behind the same seam — not built until a concrete operational need surfaces.

The migration is sequenced as **10 child issues across 6 waves**, gated by two non-negotiable CI tests (lifecycle parity + import discipline). Substantial gradual benefit lands at the end of Wave B (safety net) and Wave C (cli-return becomes the default control plane, closing the entire #840 cluster).

---

## 2. Why we're doing this

### 2.1 Symptoms

| Symptom | Where it shows up |
|---|---|
| Coach knows about gh, cmux, subprocess, GitHub Projects v2, manifest format, validator dispositions, worktree creation, broken-pipe retries, persona materialization, observer lifecycle | `src/atdd/coach/commands/coach.py` (4000+ LOC mixing policy with execution) |
| Spawn pipeline fails at `paste-landed` / `prompt-submitted` race | #840 — observed multiple times this session |
| Shim primes prompt but doesn't submit | #872 — closed-but-regressed on 3.83.4 |
| Shim doesn't forward stdin | #871 — same |
| `atdd issue --status COMPLETE` doesn't update Project v2 board status field | #882 |
| `core.bare=true` repeatedly contaminates shared config from unguarded agent shells | Recurring; #884 filed to enforce at PATH-shim layer |
| Coach tests must mock subprocess, gh, cmux, filesystem — every new test fights the same mock surface | All tests under `src/atdd/coach/commands/tests/` |
| Adding a new phase or new persona requires editing code in multiple places | `coach.py`, `spawn.py`, `session_template.py`, conventions YAML |

### 2.2 Root cause

Coach is **five jobs in one module**:

1. **Policy** — "what phase comes next given evidence?"
2. **Workflow** — "drive an issue through its phases over time, resume on crash, fan out waves"
3. **Runtime** — "create worktrees, spawn shims, attach observers"
4. **Agent control** — "deliver prompts, detect readiness, forward stdin, handle done signals"
5. **Integrations** — "label issues, sync Projects v2, merge PRs"

Each of these evolves on a different cadence with different concerns. Coupling them prevents independent improvement and makes every change a coordination problem.

---

## 3. Target architecture

### 3.1 Layer map

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ CLI                                                                          │
│   atdd.cli                                                                   │
│   atdd.coach.commands.coach           (THIN SHELL — public command surface)  │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │ invokes
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ TRAIN RUNNER (stateful runner; orchestrates phases over time)                    │
│   atdd.train.runner_iface          TrainRunner protocol                │
│   atdd.train.runners.jsonl          JsonlTrainRunner (default)          │
│   atdd.train.runners.temporal       reserved name; not implemented         │
│   atdd.train.runners.langgraph_review      reserved name; not implemented         │
│   atdd.train.issue_runner          drive_single_issue, event loop         │
│   atdd.train.wave_runner           concurrent wave execution              │
│   atdd.train.events                event types, dispatch                  │
│   atdd.train.resume                replay + reconcile                     │
│   atdd.train.persistence           PersistenceStore impl;                 │
│                                       materializes Evidence for Coach        │
└───────┬──────────────┬──────────────────┬─────────────────────┬─────────────┘
        │ calls (pure) │ calls            │ calls               │ calls
        ▼              ▼                  ▼                     ▼
┌──────────────┐ ┌──────────────────┐ ┌──────────────────────┐ ┌──────────────┐
│ COACH-CORE   │ │ RUNTIME          │ │ INTEGRATIONS         │ │ VALIDATORS   │
│ pure policy  │ │ worktree         │ │ github.issue_state   │ │ planner/     │
│              │ │ multiplexer      │ │ github.projects_v2   │ │ tester/      │
│ no I/O       │ │ agent_control    │ │ github.pr            │ │ coder/       │
│ no subproc   │ │                  │ │ github.checks        │ │ coach        │
│ no gh        │ │                  │ │                      │ │              │
│ no cmux      │ │                  │ │                      │ │ emit         │
│ no threading │ │                  │ │                      │ │ Validator    │
│              │ │                  │ │                      │ │ Report       │
└──────────────┘ └──────────────────┘ └──────────────────────┘ └──────────────┘
                          │                                              │
                          │                                              ▼
                          │                                    reports flow back
                          │                                    via persistence
                          ▼
                ┌─────────────────────────────────────────┐
                │ OBSERVER                                 │
                │ atdd.observer                            │
                │ first-class READ-ONLY consumer of:       │
                │   - events.jsonl                         │
                │   - per-agent output.log                 │
                │ NEVER writes to either                   │
                └─────────────────────────────────────────┘
```

### 3.1.1 ATDD-native naming correction

This document uses **Train** and **TrainRunner** as the canonical ATDD vocabulary:

| Term | Meaning |
|---|---|
| **Train** | Domain route: phase machine, WMBT/claim dependency graph, acceptance path, evidence requirements, persona/prompt mapping. It is data/policy input, not an execution engine. |
| **Coach-core** | Pure policy authority: decides whether a train may advance, block, stay, escalate, or merge. |
| **TrainRunner** | Stateful execution layer: creates runs, materializes evidence, records events, dispatches agents, waits, resumes, runs waves, and calls runtime/integration adapters. |
| **JsonlTrainRunner** | The first/default TrainRunner implementation. It is the local JSONL-backed runner. |
| **TemporalTrainRunner** | Reserved future TrainRunner backend, only if JSONL durability/concurrency proves insufficient. |
| **LangGraphReviewRunner** | Reserved future review/judge subgraph, not the whole lifecycle runner. |

Rule: **Train is not the Temporal/LangGraph-equivalent. TrainRunner is the equivalent layer/interface.**

### 3.2 Layer responsibilities

| Layer | Owns | Does NOT own |
|---|---|---|
| **`atdd.coach.core`** | Phase machine, transition rules, evidence-evaluation rules, persona/prompt-template mapping, merge-readiness rules, escalation policy. Pure functions of (Evidence, Conventions). | Any I/O, any state, any subprocess, any external API |
| **`atdd.train`** | Stateful orchestration: sessions, retries, event loop, wave concurrency, resume, persistence reads/writes, conventions loading | Phase semantics, persona mapping, spawn mechanics, GitHub API calls |
| **`atdd.runtime.worktree`** | git worktree create/remove, branch safety, working-tree invariants | Phase decisions, GitHub label state |
| **`atdd.integrations.github`** | Issue labels, Projects v2 fields, PR state/merge, check runs | Phase semantics, decision logic |
| **`atdd.validators`** | Run validation against repo state, emit `ValidatorReport` rows | Decide what to do with violations |
| **`atdd.observer`** | Read events.jsonl + per-agent output.log; surface in CLI/TUI | Write any orchestration state |

### 3.3 Dependency rules (validator-enforced)

| Layer | MAY import | MUST NOT import |
|---|---|---|
| `atdd.coach.core` | stdlib only; `dataclasses`, `typing`, `enum`, `pathlib` (types only, no opens) | `subprocess`, `os.system`, `requests`, `urllib`, `gh`, `git`, `cmux`, `time.sleep`, `threading`, `multiprocessing`, `asyncio`, `atdd.runtime.*`, `atdd.integrations.*`, `atdd.train.*`, `atdd.observer`, any I/O |
| `atdd.train.*` | `atdd.coach.core`, `atdd.runtime.*`, `atdd.integrations.*`, `atdd.validators` (for type imports), stdlib | `atdd.cli` (cycle), `atdd.observer` |
| `atdd.runtime.worktree` | stdlib, `subprocess`, `pathlib` | `atdd.coach.*`, `atdd.train.*`, `atdd.integrations.*` |
| `atdd.integrations.github.*` | stdlib, `subprocess` (gh CLI), `json` | `atdd.coach.*`, `atdd.train.*`, `atdd.runtime.*` |
| `atdd.validators` | stdlib, target subject under test, `atdd.coach.conventions` (yaml load for rule lookup) | orchestration layers |
| `atdd.observer` | stdlib, `atdd.train.persistence` (read-only API) | any writer |

These rules are enforced by `tests/architecture/test_layer_imports.py` (see [Appendix A](#appendix-a-import-discipline-test)).

### 3.4 Public CLI surface — UNCHANGED

| Command | Behavior |
|---|---|
| `atdd coach <N>` | Drive issue #N through its lifecycle (now via TrainRunner) |
| `atdd issue <slug \| N>` | Create / enter an issue (unchanged) |
| `atdd pr <N>` | Open / view PR for issue #N (unchanged) |
| `atdd validate [phase]` | Run validators (unchanged surface; emission format changes per Child 3) |
| `atdd agent done` | Worker signals completion (unchanged surface; internal channel changes per Child 9) |
| `atdd resume <run_id>` | **NEW** — replay a train run (added in Child 9) |
| `atdd observer` | Live event-stream view (unchanged surface; promoted to first-class in Child 10) |

Operator-facing behavior MUST be invariant from Child 1 through Child 10 except where a child explicitly adds a new command (only Child 9 adds `atdd resume`).

---

## 4. Typed contracts

All types live in `atdd.coach.core.types` and are **frozen dataclasses** unless noted. Coach-core owns these types because everyone else consumes them; defining them in policy keeps the dependency direction inward.

### 4.1 Coach-core enums

```python
class Phase(StrEnum):
    INIT = "INIT"
    PLANNED = "PLANNED"
    RED = "RED"
    GREEN = "GREEN"
    SMOKE = "SMOKE"
    REFACTOR = "REFACTOR"
    COMPLETE = "COMPLETE"
    BLOCKED = "BLOCKED"
    OBSOLETE = "OBSOLETE"

class Persona(StrEnum):
    PLANNER = "planner"
    TESTER = "tester"
    CODER = "coder"
    REVIEWER = "reviewer"

class IssueType(StrEnum):
    IMPLEMENTATION = "implementation"
    FIX = "fix"
    CHORE = "chore"
    REFACTOR = "refactor"
    CLEANUP = "cleanup"
    DOCS = "docs"

class CiState(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    PENDING = "pending"
    NONE = "none"

class VerdictKind(StrEnum):
    PROCEED = "proceed"   # advance to to_phase, dispatch persona
    STAY = "stay"         # remain in current phase; e.g. waiting on CI
    BLOCKED = "blocked"   # cannot advance; operator surface; do not retry
    ESCALATE = "escalate" # operator MUST intervene; pause run
```

### 4.2 Coach-core data types

```python
@dataclass(frozen=True)
class WmbtRef:
    wmbt_id: str                 # e.g. "wmbt:govern-lifecycle:E032"
    wagon: str
    acceptances: tuple[str, ...] # urn strings

@dataclass(frozen=True)
class ValidatorReport:
    validator_id: str            # e.g. "issue_body_has_graph_context"
    rule_id: str                 # canonical rule id
    severity: int                # 0-5
    disposition: str             # "block" | "warn-and-log" | "suppress-and-clean"
    unsuppressed_count: int      # how many violations remain after suppress markers
    location: str | None = None  # file:line or external ref
    detail: str | None = None    # short human-readable
    fix_hint_ref: str | None = None

@dataclass(frozen=True)
class PrState:
    number: int
    state: Literal["OPEN", "MERGED", "CLOSED"]
    mergeable: Literal["MERGEABLE", "CONFLICTING", "UNKNOWN"]
    merge_state: Literal["CLEAN", "BLOCKED", "BEHIND", "UNSTABLE", "DIRTY", "UNKNOWN"]
    head_sha: str
    check_runs: tuple["CheckRun", ...]
    reviews: tuple["Review", ...]
    closes_issues: tuple[int, ...]

@dataclass(frozen=True)
class CheckRun:
    name: str
    conclusion: Literal["SUCCESS", "FAILURE", "NEUTRAL", "CANCELLED", "TIMED_OUT", "PENDING", "NONE"]
    workflow_id: int | None

@dataclass(frozen=True)
class Review:
    reviewer: str
    state: Literal["APPROVED", "CHANGES_REQUESTED", "COMMENTED", "DISMISSED"]
    submitted_at: str            # ISO-8601

@dataclass(frozen=True)
class Evidence:
    """Everything Coach needs to decide, materialized by train.persistence at one instant."""
    issue_number: int
    issue_type: IssueType
    current_phase: Phase
    train_id: str | None
    branch: str
    wmbts: tuple[WmbtRef, ...]
    validator_reports: tuple[ValidatorReport, ...]
    ci_state: CiState
    pr_state: PrState | None
    last_commit_sha: str
    artifacts_present: frozenset[str]   # e.g. {"PLAN_COMMIT", "RED_TESTS", "GREEN_IMPL", "SMOKE_VERIFIED"}
    elapsed_in_phase_seconds: int
    conventions_hash: str               # ties Evidence to a Conventions snapshot

@dataclass(frozen=True)
class Verdict:
    kind: VerdictKind
    reason: str                  # human-readable; surfaced to operator
    rule_ids: tuple[str, ...]    # conventions that justify this verdict
    fix_hint: str | None = None  # for BLOCKED / ESCALATE: actionable next step
    retry_after_seconds: int | None = None  # for STAY: optional backoff hint

@dataclass(frozen=True)
class TransitionDecision:
    from_phase: Phase
    to_phase: Phase | None       # None when verdict.kind != PROCEED
    persona: Persona | None      # who runs next; None when not PROCEED
    prompt_template_id: str | None
    evidence_keys_required: tuple[str, ...]  # what evidence the worker will need
    verdict: Verdict             # PROCEED ⇒ dispatch; others ⇒ train runner surfaces

@dataclass(frozen=True)
class MergeVerdict:
    can_merge: bool
    blockers: tuple[str, ...]    # validator IDs or lifecycle reasons
    required_label: Phase | None # e.g. REFACTOR or COMPLETE before merge

@dataclass(frozen=True)
class PhaseSpec:
    name: Phase
    agent: Persona | None
    transitions_to: tuple[Phase, ...]
    pre_commit_gate: str | None  # CLI command if any

@dataclass(frozen=True)
class RuleSpec:
    rule_id: str
    severity: int
    disposition: str
    fix_hint: str

@dataclass(frozen=True)
class Conventions:
    """The frozen policy bundle Coach-core needs. Loaded by train.persistence."""
    phase_machine: Mapping[Phase, PhaseSpec]
    rules: Mapping[str, RuleSpec]
    prompt_templates: Mapping[str, str]   # template_id → fully rendered text
    snapshot_hash: str                    # sha256 of normalized source files
    snapshot_paths: tuple[str, ...]       # source files contributing to the snapshot
```

### 4.3 Coach-core pure functions

```python
# atdd/coach/core/__init__.py — the only public API

def next_transition(
    evidence: Evidence,
    conventions: Conventions,
) -> TransitionDecision:
    """Pure. Look up the current phase, evaluate gates, return decision.
    Never reads files, never calls gh, never spawns anything.
    """

def evaluate_evidence(
    evidence: Evidence,
    conventions: Conventions,
) -> Verdict:
    """Pure. Given evidence, is the current phase satisfied? PROCEED/STAY/BLOCKED."""

def review_phase_output(
    phase: Phase,
    reports: tuple[ValidatorReport, ...],
    conventions: Conventions,
) -> Verdict:
    """Pure. Given validator reports, has this phase's exit criteria been met?"""

def merge_readiness(
    evidence: Evidence,
    conventions: Conventions,
) -> MergeVerdict:
    """Pure. Can the PR for this issue be merged right now?"""

def escalation_for(
    evidence: Evidence,
    conventions: Conventions,
) -> Verdict | None:
    """Pure. Detect escalation conditions (stuck phase, conflicting evidence,
    irrecoverable state). Returns None when nothing to escalate.
    """
```

**Properties Coach-core MUST satisfy:**

1. Every function is pure: same inputs always produce the same output.
2. No function imports anything that does I/O (enforced by [Appendix A test](#appendix-a-import-discipline-test)).
3. Every function is exhaustively table-tested with no mocking required.
4. Adding a new phase = editing `phase_machine.convention.yaml` + (optionally) adding rules; **no code change in Coach-core**.

### 4.4 Conventions snapshot

Conventions are **loaded once per run** by `train.persistence.load_conventions()` and frozen for the run's duration. The snapshot's hash is recorded in the run's first event so replay produces identical decisions.

```python
# atdd/train/persistence.py
def load_conventions(repo_root: Path) -> Conventions:
    """Load + normalize conventions YAML files, compute snapshot hash, freeze."""
```

Hot-reload mid-run is explicitly NOT supported. To pick up convention changes, start a new run (`atdd coach <N>` produces a new run_id with a new snapshot).

### 4.5 Phase machine as data

The phase machine MUST live in YAML as the single source of truth:

```yaml
# src/atdd/coach/conventions/phase_machine.convention.yaml
phases:
  INIT:
    agent: planner
    transitions_to: [PLANNED, BLOCKED, OBSOLETE]
    pre_commit_gate: "atdd validate planner --local --skip-api"
  PLANNED:
    agent: tester
    transitions_to: [RED, BLOCKED, OBSOLETE]
  RED:
    agent: coder
    transitions_to: [GREEN, BLOCKED, OBSOLETE]
  GREEN:
    agent: tester
    transitions_to: [SMOKE, BLOCKED, OBSOLETE]
  SMOKE:
    agent: coder
    transitions_to: [REFACTOR, BLOCKED, OBSOLETE]
  REFACTOR:
    agent: coder
    transitions_to: [COMPLETE, BLOCKED, OBSOLETE]
  COMPLETE:
    agent: null
    transitions_to: []
  BLOCKED:
    agent: null
    transitions_to: [INIT, PLANNED, RED, GREEN, SMOKE, REFACTOR, OBSOLETE]
  OBSOLETE:
    agent: null
    transitions_to: []
```

The existing duplicate in `CLAUDE.md::state_machine.transitions` MUST be removed in Child 1 (CLAUDE.md is generated from conventions).

### 4.6 PersistenceStore protocol

```python
# atdd/train/persistence.py

class PersistenceStore(Protocol):
    # --- run lifecycle ---
    def create_run(self, issue_number: int, *, conventions: Conventions) -> RunId: ...
    def load_run(self, run_id: RunId) -> RunState: ...
    def list_runs(self, *, status: RunStatus | None = None) -> list[RunSummary]: ...

    # --- events (single-writer: train runner) ---
    def append_event(self, run_id: RunId, event: TrainEvent) -> None: ...
    def replay_events(self, run_id: RunId) -> Iterator[TrainEvent]: ...

    # --- decisions (audit trail for every Coach Verdict) ---
    def append_decision(self, run_id: RunId, decision: TransitionDecision, *, evidence_hash: str) -> None: ...

    # --- manifest (issue registry) ---
    def get_issue(self, n: int) -> IssueRecord: ...
    def upsert_issue(self, rec: IssueRecord) -> None: ...

    # --- evidence materialization (THE bridge to Coach-core) ---
    def materialize_evidence(self, issue_number: int) -> Evidence:
        """Aggregate from: manifest, GitHub adapter, validators, filesystem.
        Returns a frozen snapshot. Conventions hash MUST match the current Conventions.
        """
```

Implementations:

| Class | Status | Notes |
|---|---|---|
| `JsonlPersistenceStore` | Ships in Child 7 | Default; backs to filesystem under `runtime/runs/<run_id>/` |
| `InMemoryPersistenceStore` | Ships in Child 2 | Test fixture for parity test |

### 4.7 TrainRunner protocol

```python
# atdd/train/runner_iface.py

class TrainRunner(Protocol):
    def start_issue(
        self,
        issue_number: int,
        *,
        policy: PolicyHandle,
    ) -> RunId: ...

    def resume(self, run_id: RunId) -> None: ...

    def run_wave(
        self,
        issue_numbers: list[int],
        *,
        concurrency: int = 1,
    ) -> WaveResult: ...

    def handle_event(self, run_id: RunId, event: TrainEvent) -> None: ...

    def status(self, run_id: RunId) -> RunStatus: ...

    def cancel(self, run_id: RunId, *, reason: str) -> None: ...


@dataclass(frozen=True)
class PolicyHandle:
    """Bundles Coach-core entry points + frozen Conventions. Constructed by CLI."""
    coach_module: ModuleType         # provides next_transition, evaluate_evidence, etc.
    conventions: Conventions

# --- supporting types referenced by the protocol ---
# (Shown together for protocol-readability. Physical location:
#   RunId, RunStatus, RunSummary, RunState, WaveResult, TrainEvent → atdd/train/types.py
#   IssueRecord → atdd/train/persistence.py
#   MergeResult → atdd/integrations/github/types.py
#   AgentHandle → atdd/runtime/agent_control.py — also referenced from §4.8)

RunId = NewType("RunId", str)         # opaque; e.g. "run-816-2026-05-30-a81b0d90"

@dataclass(frozen=True)
class RunStatus:
    run_id: RunId
    issue_number: int
    current_phase: Phase
    state: Literal["RUNNING", "BLOCKED", "ESCALATED", "COMPLETED", "CANCELLED"]
    last_event_seq: int
    started_at: str
    last_event_at: str

@dataclass(frozen=True)
class RunSummary:
    run_id: RunId
    issue_number: int
    state: Literal["RUNNING", "BLOCKED", "ESCALATED", "COMPLETED", "CANCELLED"]

@dataclass(frozen=True)
class RunState:
    """Materialized in-memory state reconstructed from event replay."""
    run_id: RunId
    issue_number: int
    current_phase: Phase
    conventions_hash: str
    decisions: tuple[TransitionDecision, ...]
    last_event_seq: int

@dataclass(frozen=True)
class WaveResult:
    started: tuple[RunId, ...]
    blocked: tuple[RunId, ...]
    failed_to_start: tuple[tuple[int, str], ...]  # (issue_number, reason)

@dataclass(frozen=True)
class TrainEvent:
    """Unified shape for events appended to events.jsonl (see §5.2)."""
    schema_version: str
    ts: str
    run_id: RunId
    issue_number: int
    type: str
    payload: dict
    seq: int    # monotonic per run

@dataclass(frozen=True)
class IssueRecord:
    """Manifest row shape — read/written by persistence."""
    id: str
    slug: str
    issue_number: int
    type: IssueType
    status: Phase
    train: str | None
    created: str
    archived: str | None

@dataclass(frozen=True)
class MergeResult:
    merged: bool
    merge_commit_sha: str | None
    reason: str | None    # populated when merged=False

@dataclass(frozen=True)
class AgentHandle:
    """Opaque reference to a spawned agent. Implementation-defined contents."""
    agent_id: str
    spec: DispatchSpec
    spawned_at: str
    transport: Literal["cli-return", "tui-scrape", "headless-print"]
    # implementations may carry additional private fields (pty handle, surface ref, etc.)
```

**Note:** `ModuleType` is from `types` (stdlib). `NewType` and `Literal` are from `typing`.

Implementations:

| Class | Status | When to add |
|---|---|---|
| `JsonlTrainRunner` | Ships in Child 8 | **Default** — wraps current durable JSONL behavior |
| `TemporalTrainRunner` | Reserved name only | Add only when a concrete operational deficit forces it (see [§7.2](#72-temporal-runner-deferred)) |
| `LangGraphReviewRunner` | Reserved name only | Add when judge/reviewer becomes a real multi-step graph (see [§7.3](#73-langgraph-review-subgraph-deferred-scoped)) |
| `LocalDryRunRunner` | Ships in Child 2 | Used by parity test |

### 4.8 AgentController + DispatchSpec

> **SUPERSEDED — pruned from core by #1480.** Core coach is lifecycle
> governance and does not manage sub-workers, so this layer was removed
> outright rather than relocated to a provider. The specification below is
> retained as the design record of what once shipped; it describes no
> current core module.

```python
# atdd/runtime/agent_control.py

@dataclass(frozen=True)
class DispatchSpec:
    """The typed handoff between train runner (decided what) and runtime (do it).
    Workflow constructs this from a TransitionDecision; runtime executes it.
    """
    agent_id: str                # e.g. "tester-816-a81b0d90"
    persona: str                 # carries a Persona value; typed str (see note)
    worktree_path: Path
    prompt_text: str             # FULLY RENDERED — train runner did template substitution
    correction_inbox: Path       # cli-return.jsonl
    output_log: Path
    runtime_dir: Path
    env_overrides: dict[str, str]
    transport: Literal["cli-return", "tui-scrape", "headless-print"]
    permission_mode: Literal["acceptEdits", "default", "plan"]
    allowed_tools: tuple[str, ...]
```

> **§3.3 import-discipline note (Child 6, #893):** `DispatchSpec.persona` is
> typed `str` rather than `Persona`. `Persona` lives in `atdd.coach.core.types`,
> and `atdd.runtime.agent_control` MUST NOT import `atdd.coach.*` (§3.3, enforced
> by `tests/architecture/test_layer_imports.py`). `Persona` is a `StrEnum`, so a
> `Persona` value is a valid `str` and flows through unchanged. For the same
> reason `Multiplexer.attach_view(handle)` (§4.9) types its handle argument
> structurally (`object`) instead of importing `AgentHandle` from the sibling
> runtime layer. The actual adapter argv is passed to
> the cmux-native launcher (`CmuxAgentController`, #978/#979) — which uses
> `build_dispatch_command` + `prepare`; `DispatchSpec` itself is unchanged
> from this contract.

```python
@dataclass(frozen=True)
class ReadyResult:
    is_ready: bool
    transport_signal: str        # which signal fired (e.g. "output_log_heartbeat")
    elapsed_seconds: float


@dataclass(frozen=True)
class AgentEvent:
    type: Literal["thinking", "tool_use", "phase_complete", "agent_done", "error"]
    timestamp: str
    payload: dict


class AgentSignal(StrEnum):
    INTERRUPT = "interrupt"
    DONE_ACK = "done_ack"
    PROMPT_ADDITIONAL = "prompt_additional"


class AgentController(Protocol):
    def spawn(self, spec: DispatchSpec) -> AgentHandle: ...

    def deliver_prompt(self, handle: AgentHandle, prompt: str) -> None:
        """Initial OR mid-run correction. Implementation MUST inject AND submit
        (this contract closes #872 — submit gap).
        """

    def wait_ready(self, handle: AgentHandle, *, timeout_s: float) -> ReadyResult: ...

    def stream_events(self, handle: AgentHandle) -> Iterator[AgentEvent]:
        """Yields events parsed from agent's output. cli-return: heartbeat + structured
        events. tui-scrape: screen-scrape markers (deprecated path).
        """

    def signal(self, handle: AgentHandle, sig: AgentSignal) -> None:
        """Including stdin forwarding for INTERRUPT (closes #871 — stdin gap)."""

    def stop(self, handle: AgentHandle, *, reason: str) -> None: ...
```

Implementations (historical Child-6 decomposition):

> **Superseded (#978/#979):** the pty-owning launch transport below was replaced
> by the cmux-native launcher (`src/atdd/runtime/agent_control/cmux_launch.py`).
> This table is retained as a record of the original decomposition.

| Class | Status | Notes |
|---|---|---|
| `CmuxAgentController` | Default (#978/#979) | cmux-native: positional-prompt first turn; decisions ride the cmux Feed |
| `HeadlessPrintController` | Optional | `claude -p` for CI / non-interactive runs |

### 4.9 Multiplexer protocol (view-only)

> **SUPERSEDED — pruned from core by #1480.** Core coach is lifecycle
> governance and does not manage sub-workers, so this layer was removed
> outright rather than relocated to a provider. The specification below is
> retained as the design record of what once shipped; it describes no
> current core module.

```python
# atdd/runtime/multiplexer.py

class Multiplexer(Protocol):
    def attach_view(self, handle: AgentHandle) -> SurfaceRef:
        """Open a pane and tail handle.output_log into it."""

    def list_surfaces(self) -> list[SurfaceRef]: ...

    def close_surface(self, ref: SurfaceRef) -> None: ...

    def list_workspaces(self) -> list[WorkspaceRef]: ...
```

**Forbidden methods** (would re-introduce screen-scrape control):

- `paste_text` — control path; belongs in `AgentController.deliver_prompt`
- `send_key` — control path; belongs in `AgentController.signal`
- `capture_pane_text` — control path; belongs in `AgentController.stream_events`

Import-discipline test asserts none of these exist on the Multiplexer protocol.

### 4.10 GitHub integration contracts

```python
# atdd/integrations/github/issue_state.py

def read_phase(issue: int) -> Phase: ...

def transition_phase(issue: int, to: Phase) -> None:
    """ATOMIC: swap label AND sync Projects v2 status field.
    Internally calls projects_v2.sync_status_field. Closes #882.
    """

def read_train(issue: int) -> str | None: ...
def set_train(issue: int, train_id: str) -> None: ...
def read_body(issue: int) -> str: ...
def update_body(issue: int, body: str) -> None: ...

# atdd/integrations/github/projects_v2.py

def sync_status_field(issue: int, phase: Phase) -> None:
    """GraphQL mutation against Projects v2. Requires PROJECT_TOKEN.
    Idempotent; safe to call repeatedly.
    """

# atdd/integrations/github/pr.py

def read_pr_state(pr: int) -> PrState: ...
def open_pr(issue: int, *, title: str, body: str) -> int: ...
def merge_pr(pr: int, *, strategy: Literal["squash","merge","rebase"]) -> MergeResult: ...
def update_branch(pr: int) -> None: ...

# atdd/integrations/github/checks.py

def read_check_runs(sha: str) -> tuple[CheckRun, ...]: ...
def trigger_rerun(run_id: int) -> None: ...
```

Every integration call returns plain data (no Coach types). `train.persistence.materialize_evidence()` translates GitHub responses into `Evidence`.

### 4.11 Validator emission contract

Every validator MUST emit `ValidatorReport` rows (defined in §4.2). Adopted via Child 3.

```python
# pattern every validator follows
from atdd.coach.core.types import ValidatorReport
from atdd.validators.emit import emit_reports

def test_my_validator(...):
    reports = []
    for violation in compute_violations(...):
        reports.append(ValidatorReport(
            validator_id="my_validator",
            rule_id="planner.foo.bar",
            severity=3,
            disposition="warn-and-log",
            unsuppressed_count=1,
            location=str(violation.path),
            detail=violation.message,
        ))
    emit_reports(reports)              # persisted under runs/<id>/validator-reports.jsonl
    assert_disposition_satisfied(...)  # existing gate continues to work
```

`emit_reports()` writes to the run's persistence store so `materialize_evidence()` can read them back into `Evidence.validator_reports`.

---

## 5. Runtime data model

### 5.1 Filesystem layout

```
<repo-root>/
├── .atdd/
│   ├── manifest.yaml                 # issue registry (read by train.persistence)
│   ├── config.yaml                   # repo-level config
│   ├── EMERGENCY_BYPASS              # ephemeral (5-min TTL)
│   ├── emergency-audit.jsonl         # append-only
│   └── runtime/
│       ├── runs/
│       │   └── <run_id>/
│       │       ├── events.jsonl              # single-writer: train runner
│       │       ├── decisions.jsonl           # every Coach Verdict + evidence hash
│       │       ├── conventions.snapshot.yaml # frozen Conventions for this run
│       │       ├── conventions.hash          # sha256 of the snapshot
│       │       ├── dispatch.jsonl            # DispatchSpec written → consumed by runtime
│       │       └── status.json               # last-known phase/agent_id/pr_number
│       ├── agents/
│       │   └── <agent_id>/                   # per-agent state
│       │       ├── manifest.json
│       │       ├── cli-return.jsonl          # correction inbox
│       │       ├── output.log                # tee'd from wrapped TUI
│       │       └── events.jsonl              # parsed AgentEvent stream
│       └── tool_use_audit.jsonl              # forbidden-command classifier log
```

### 5.2 events.jsonl schema

Single-writer (train runner). Schema-versioned. Append-only.

```jsonc
// Every line is a JSON object with these required fields:
{
  "schema_version": "1.0",
  "ts": "2026-05-30T10:23:45.123Z",
  "run_id": "...",
  "issue_number": 816,
  "type": "...",              // see event types below
  "payload": { /* type-specific */ }
}
```

**Single-writer rule:** the **train-runner layer** is the sole writer to `events.jsonl`. Specifically, `train.issue_runner` and `train.resume` are the only modules that call `persistence.append_event()`. Runtime and integrations *produce* events but never persist them directly — they emit via callbacks/iterators that train runner drains and appends. This single-writer invariant is what makes replay deterministic.

**Event types (initial set):**

| `type` | Required payload fields | Sourced from |
|---|---|---|
| `RunStarted` | `conventions_hash`, `conventions_snapshot_ref`, `policy_handle_id` | train.issue_runner (self) |
| `EvidenceMaterialized` | `evidence_hash`, `current_phase` | train.issue_runner (calling persistence.materialize_evidence) |
| `DecisionMade` | `verdict_kind`, `from_phase`, `to_phase`, `persona`, `rule_ids` | train.issue_runner (calling coach.core.next_transition) |
| `DispatchEmitted` | `dispatch_spec` (full DispatchSpec serialized) | train.issue_runner (self) |
| `AgentSpawned` | `agent_id`, `transport`, `surface_ref` | train.issue_runner (after runtime.agent_control.spawn returns) |
| `AgentReady` | `agent_id`, `transport_signal`, `elapsed_seconds` | train.issue_runner (after runtime.agent_control.wait_ready returns) |
| `AgentEventReceived` | `agent_id`, `agent_event` | train.issue_runner (draining runtime.agent_control.stream_events) |
| `AgentDone` | `agent_id`, `summary`, `exit_code` | train.issue_runner (on `atdd agent done` signal arrival) |
| `PhaseAdvanced` | `from_phase`, `to_phase`, `commit_sha` | train.issue_runner (after integrations.github.issue_state.transition_phase) |
| `PrOpened` | `pr_number`, `branch` | train.issue_runner (after integrations.github.pr.open_pr) |
| `PrMerged` | `pr_number`, `merge_commit_sha` | train.issue_runner (after integrations.github.pr.merge_pr) |
| `RunBlocked` | `verdict` (full Verdict serialized) | train.issue_runner (self) |
| `RunEscalated` | `verdict`, `notification_channel` | train.issue_runner (self) |
| `RunCompleted` | `final_phase`, `total_duration_seconds` | train.issue_runner (self) |
| `RunResumed` | `from_event_seq`, `resume_reason` | train.resume (self) |

`policy_handle_id` is `sha256(coach_module.__name__ + conventions.snapshot_hash)` — uniquely identifies the policy that produced every decision in the run.

**Schema-version rule:** any `type` change OR payload-shape change increments minor; breaking format change increments major. Replay refuses unknown major versions; reader migrates minor versions in-memory.

### 5.3 Conventions snapshot

`runs/<run_id>/conventions.snapshot.yaml` contains the merged, normalized content of every convention YAML the run depended on. `conventions.hash` is `sha256(normalized snapshot bytes)`. The hash appears in `RunStarted.payload.conventions_hash` and in every `DecisionMade` event's `evidence_hash` derivation.

Resume reads the snapshot from disk; it does NOT re-read source conventions (which may have changed since the run started). This guarantees replay determinism.

### 5.4 Manifest

Existing format preserved. `train.persistence.get_issue()` and `upsert_issue()` are the only modifiers. Existing pre-commit and pre-push hooks continue to gate manifest writes.

---

## 6. End-to-end event flow

### 6.1 Successful issue lifecycle (sequence)

```
operator ─► atdd coach 816
              │
              ▼
        cli.coach_cmd
              │
              ▼
        train.persistence.load_conventions()  ─► Conventions(hash=sha256:abc…)
              │
              ▼
        TrainRunner.start_issue(816, PolicyHandle(coach, conventions))
              │
              ├─► persistence.create_run() ─► run_id, writes RunStarted event
              │
              ▼
        ┌─────────────────────────  EVENT LOOP  ─────────────────────────┐
        │                                                                │
        │  persistence.materialize_evidence(816) ─┐                      │
        │    ↑ reads: manifest, gh adapter,       │                      │
        │      validators, fs artifacts           │                      │
        │                                          │                      │
        │  Evidence(current_phase=GREEN, ...) ────┘                      │
        │    │ writes EvidenceMaterialized event                         │
        │    ▼                                                            │
        │  coach.core.next_transition(evidence, conventions)             │
        │    │ writes DecisionMade event                                  │
        │    │ writes decisions.jsonl row                                 │
        │    ▼                                                            │
        │  ┌─────────────────┬────────────────────┬─────────────────────┐ │
        │  │ PROCEED         │ STAY               │ BLOCKED/ESCALATE    │ │
        │  ▼                 ▼                    ▼                     │ │
        │ train.dispatch     train.wait           train.surface         │ │
        │   build DispatchSpec  schedule next     verdict to operator   │ │
        │   write Dispatch-    materialization    write RunBlocked or   │ │
        │     Emitted event    after backoff      RunEscalated event    │ │
        │   runtime.worktree   loop ↺              loop exit            │ │
        │     .ensure_issue                                              │ │
        │     _worktree()                                                │ │
        │   runtime.agent_                                                │ │
        │     control.spawn()                                            │ │
        │   runtime.agent_                                                │ │
        │     control.deliver                                            │ │
        │     _prompt()                                                  │ │
        │   runtime.agent_                                                │ │
        │     control.wait_ready                                         │ │
        │     ()                                                         │ │
        │   multiplexer.attach                                            │ │
        │     _view(handle)                                              │ │
        │     (observability                                              │ │
        │     only, optional)                                            │ │
        │   write AgentSpawned                                            │ │
        │     event                                                      │ │
        │  │                                                              │ │
        │  ▼                                                              │ │
        │  worker runs (RED tests, GREEN code, ...)                       │ │
        │    writes commits, pushes                                       │ │
        │    streams events via agent_control.stream_events               │ │
        │    each event → write AgentEventReceived                       │ │
        │    finally calls `atdd agent done`                              │ │
        │    → write AgentDone event                                      │ │
        │  │                                                              │ │
        │  ▼                                                              │ │
        │  loop ↺ (back to materialize_evidence)                          │ │
        │                                                                  │
        └─────────────────────────────────────────────────────────────────┘
              │
              ▼ (at REFACTOR with PR open + checks green)
        coach.core.merge_readiness(evidence, conventions) ─► can_merge=true
              │
              ▼
        integrations.github.pr.merge_pr(883, strategy="squash")
        integrations.github.issue_state.transition_phase(816, COMPLETE)
          └─ ATOMICALLY label swap + projects_v2.sync_status_field
        train.cleanup: worktree, surfaces, run dir snapshot
        write PrMerged + PhaseAdvanced + RunCompleted events
```

### 6.2 BLOCKED / ESCALATE handling

| Verdict | TrainRunner action | Operator visibility |
|---|---|---|
| `PROCEED` | Build DispatchSpec, spawn agent | Normal stream |
| `STAY` | Schedule next materialization after `retry_after_seconds` (default 60s) | Normal stream |
| `BLOCKED` | Write `RunBlocked` event, halt this run, surface verdict reason + fix_hint | `atdd observer` highlights; operator must address |
| `ESCALATE` | Write `RunEscalated` event, halt, send notification (channel per config), surface verdict | Highest-priority surface |

`BLOCKED` is recoverable: operator addresses the issue (e.g., adds a missing dependency tag), then runs `atdd resume <run_id>`. `ESCALATE` is a stronger signal that humans must intervene (e.g., the rule itself is contradictory).

### 6.3 Resume semantics

`atdd resume <run_id>`:

1. Load run's `conventions.snapshot.yaml` (NOT current source conventions).
2. Replay `events.jsonl` to reconstruct in-memory `RunState`.
3. Re-materialize evidence (current GitHub/filesystem state).
4. Call `coach.core.next_transition()` with the FROZEN conventions.
5. Continue from the next event the loop would have written.

Determinism guarantee: given identical `(events.jsonl, conventions.snapshot.yaml, current external state)`, resume produces identical decisions.

### 6.4 `atdd agent done` signal path

| Runner | Mechanism |
|---|---|
| `JsonlTrainRunner` | Worker writes a sentinel line to the agent's `events.jsonl`; runtime.agent_control detects via file watcher and forwards to train-runner event loop |
| `TemporalTrainRunner` (future) | Worker sends a Temporal Signal to the workflow handle |

The CLI surface (`atdd agent done --summary "..."`) is unchanged; the internal channel is selected by the active runner.

---

## 7. Orchestration runners

### 7.1 JSONL runner (default, ships first)

`JsonlTrainRunner` IS the migration's only runner. It wraps today's behavior with the typed contracts:

- Single-host execution
- Durable via `events.jsonl` + `decisions.jsonl` (append-only)
- Crash-recovery via `atdd resume <run_id>`
- File-watcher-based event detection (`atdd agent done`, CI webhook polling)
- Per-host concurrency limit (config: `train.concurrency.max_parallel_issues`)

Failure modes and how they're handled:

| Failure | Handling |
|---|---|
| Coach process crashes mid-loop | Events on disk; `atdd resume` reconstructs |
| Agent process crashes | `AgentDone` never written; resume re-emits `DispatchEmitted` after timeout |
| GitHub API down | Materialization returns `Evidence` with `ci_state=NONE`; Coach returns `STAY` with backoff hint |
| Worktree disappears | Persistence detects; emits `RunBlocked` with fix_hint to recreate |

### 7.2 Temporal runner (deferred)

Reserved name: `atdd.train.runners.temporal.TemporalTrainRunner`. **Not implemented.** Add only when a concrete operational deficit forces it. Gating criterion: a documented JSONL crash-recovery failure that Temporal's exactly-once activity semantics would prevent.

Design constraints captured for future implementation. (Note: in this section the word "workflow" refers to **Temporal's own** `@workflow.defn` decorator and its `workflow.patched`/`workflow.wait_condition` API — Temporal's vocabulary, not ours. Our equivalent is `TrainRunner`.)

- Coach-core stays pure; Temporal does not see Coach types.
- TrainRunner function is deterministic; `coach.core.next_transition` is called from inside the Temporal workflow (it's pure, so safe).
- Activities (non-deterministic): `materialize_evidence`, `build_dispatch_spec`, `dispatch_agent`, `merge_pr`, etc.
- `dispatch_agent` activity returns FAST after spawning; workflow `await workflow.wait_condition(lambda: state.agent_done)` until signal arrives. `atdd agent done` sends a Temporal Signal.
- Workflow versioning policy: every workflow function change MUST use `workflow.patched()` or new workflow name.
- Operational surface: cluster/cloud, workers, namespace, monitoring, retention policy — all documented in a separate operator doc when adopted.

### 7.3 LangGraph review subgraph (deferred, scoped)

Reserved name: `atdd.train.runners.langgraph_review.LangGraphReviewRunner`. **Not implemented.**

Scope (when added): the **judge/reviewer** subgraph only. Plugs into the active outer TrainRunner (JsonlTrainRunner or TemporalTrainRunner) as an embedded reasoning step that produces a `Verdict`. Does NOT replace the outer lifecycle.

### 7.4 CLI + config surface

```bash
# Today and forever:
atdd coach <N>

# Reserved in CLI now, only `jsonl` valid initially:
atdd coach <N> --runner jsonl
atdd coach <N> --runner temporal     # raises NotImplementedError until Temporal lands
atdd coach <N> --runner langgraph    # raises NotImplementedError until LangGraph lands

# Resume (new in Child 9):
atdd resume <run_id>
```

```yaml
# .atdd/config.yaml
train:
  runner: jsonl                  # jsonl | temporal | langgraph
  concurrency:
    max_parallel_issues: 4
  resume:
    auto_resume_on_start: false  # if true, atdd coach <N> resumes existing run for N
  conventions:
    snapshot_on_run_start: true  # always true; here for visibility
```

---

## 8. Observer

`atdd.observer` becomes a **first-class read-only consumer**:

- Reads `events.jsonl` (single-writer: train runner) and per-agent `output.log` (single-writer: agent_control)
- NEVER writes to either
- Surfaces a live stream in CLI/TUI
- Aggregates across active runs

Removing observer side-effects (currently coach.py has scattered observer launch/lifecycle code) is part of Child 10.

---

## 9. Invariants and incident defenses

These behaviors MUST be preserved at the same defense layer they currently sit. Each child PR that touches a layer MUST list which of these it preserves and reference the test that proves it.

| # | Defense | Bug it prevents | New owning layer | Test to add/preserve |
|---|---|---|---|---|
| I-1 | No bare-directory worktree dispatch | Dispatching to a worktree that's not a valid working tree | `runtime.worktree.ensure_issue_worktree` | `tests/runtime/test_worktree_safety::test_refuses_bare_dispatch` |
| I-2 | No protected-main commits | Direct commits to `main` from a stash recovery | `runtime.worktree` (pre-flight check) | `tests/runtime/test_worktree_safety::test_blocks_main_commit` |
| I-3 | Stale `done.json` baseline detection | Acting on a previous run's done signal | `train.events` (event id matching) | `tests/train/test_event_replay::test_rejects_stale_done` |
| I-4 | cmux broken-pipe retry on >=0.64.7 | Lost connection to multiplexer mid-spawn | `runtime.agent_control` (retry policy) | `tests/runtime/test_agent_control::test_broken_pipe_retries` |
| I-5 | Persona materialization check | Spawning the wrong persona for the phase | `coach.core.next_transition` (returns Persona) + `train.dispatch` (asserts spec.persona matches decision.persona) | `tests/coach/test_next_transition::test_persona_matches_phase` |
| I-6 | Single observer lifecycle | Multiple observers writing the same log | `observer` (singleton enforced) | `tests/observer/test_singleton` |
| I-7 | No-progress TTL | Stuck run burns infinite time | `train.issue_runner` (configurable TTL → `escalation_for` returns ESCALATE) | `tests/train/test_ttl_escalation` |
| I-8 | Durable decision-before-action | Side-effect happens before decision is persisted; resume loses ground | `train.issue_runner` (persistence.append_decision before any side effect) | `tests/train/test_decision_durability` |
| I-9 | `core.bare=false` per-worktree on creation | Shared `core.bare=true` cascades | `runtime.worktree.ensure_issue_worktree` (sets `--worktree core.bare false`) | `tests/runtime/test_worktree_safety::test_sets_per_worktree_core_bare` |
| I-10 | Forbidden-command guard (PATH shim) | Unguarded `git config core.bare true` | RETIRED by #1480 — `runtime.agent_control` pruned from core; the PATH-shim defense (#884) is unaffected | _(core-side pin retired)_ |
| I-11 | Emergency bypass 5-min TTL + audit log | Permanent bypasses | `atdd.coach.commands.emergency` (unchanged) | Existing test |
| I-12 | Issue advancement BEFORE partial-PR merge | Post-merge race causes stale CI to fail `test_issue_advancement` | `train.issue_runner` (transition_phase before merge_pr) | `tests/train/test_advancement_before_merge` |
| I-13 | Pre-push blocks `core.bare=true` worktrees | Mass-deletion PRs from bare-mode contamination | `.atdd/hooks/pre-push` (unchanged) | Existing test |

Tests I-1 through I-13 form the "incident-defenses suite." Each child PR's description MUST identify which subset it preserves.

---

## 10. Test gates

Two tests are **required CI** from Child 2 onward and **gate every PR** in the migration.

### 10.1 Lifecycle parity test

Location: `tests/lifecycle/test_full_issue_parity.py`

```python
@pytest.mark.parity
def test_full_lifecycle_init_to_complete(tmp_repo, fake_github, fake_agent, fake_observer):
    """Drive one issue INIT → COMPLETE + merged PR with all external systems mocked."""
    persistence = InMemoryPersistenceStore()
    conventions = load_conventions(tmp_repo)
    policy = PolicyHandle(coach_module=coach_core, conventions=conventions)
    runner = JsonlTrainRunner(persistence=persistence,
                                 github=fake_github,
                                 agent=fake_agent)

    issue = fake_github.create_issue(slug="parity", type=IssueType.IMPLEMENTATION)
    run_id = runner.start_issue(issue.number, policy=policy)

    # Drive the fake agent through each phase
    for expected in [Phase.PLANNED, Phase.RED, Phase.GREEN, Phase.SMOKE,
                     Phase.REFACTOR, Phase.COMPLETE]:
        fake_agent.signal_phase_done(issue.number)
        runner.handle_event(run_id, next_tick())
        assert runner.status(run_id).current_phase == expected

    # Merge gate
    assert fake_github.pr_for(issue.number).state == "MERGED"
    assert fake_github.issue(issue.number).labels == {"atdd-issue", "atdd:COMPLETE"}
    assert fake_github.project_v2_status(issue.number) == "COMPLETE"  # closes #882 verification

    # Architectural assertions
    assert_event_log_replayable(runner, run_id)
    assert_decisions_match_after_replay(runner, run_id)
    assert_no_coach_core_io_imports()
```

### 10.2 Import-discipline test

Location: `tests/architecture/test_layer_imports.py`. See [Appendix A](#appendix-a-import-discipline-test) for full code. Asserts:

- `atdd.coach.core` has zero imports of forbidden modules
- Each layer obeys its `MAY import` / `MUST NOT import` table from §3.3
- `Multiplexer` Protocol has no `paste_text` / `send_key` / `capture_pane_text` methods

### 10.3 Crash-recovery test (added in Child 9)

Location: `tests/train/test_jsonl_crash_recovery.py`

```python
def test_kill_mid_wave_then_resume_identical_decisions(tmp_repo, fake_github, fake_agent):
    """Crash JsonlTrainRunner mid-wave; verify atdd resume produces identical decisions."""
    # ... start a run, drive it 3 phases in, kill -9 ...
    # ... resume ...
    # assert: same decisions written, no double-execution
```

This test is the gate for ever adopting Temporal: if JSONL passes consistently, Temporal is not justified.

---

## 11. Compatibility and deprecation

| Surface | Policy |
|---|---|
| Public CLI commands (`atdd coach`, `atdd issue`, `atdd pr`, `atdd validate`, `atdd agent done`) | UNCHANGED throughout the migration; no version skew acceptable |
| Internal Python imports (`from atdd.coach.commands.coach import ...`) | Compatibility shims marked `@deprecated(removal="3.87.0")`; CI emits `DeprecationWarning` on use; removal PR auto-filed at version target |
| Convention YAML schemas | Backwards-compatible additions only during migration; breaking changes require explicit major version bump |
| `events.jsonl` schema | `schema_version` field; minor versions migrate in-memory at read time; major version increment requires explicit migration script |
| Old `atdd.coach.commands.coach.<private_fn>` | Removed only when no internal caller remains; documented in `CHANGELOG.md` |

Compatibility shim removal cadence:

- Marker version: shim added in Child N → marked `@deprecated`
- Soak period: 3 minor versions (e.g., added in 3.85 → warns through 3.85, 3.86, 3.87)
- Removal: at 3.88 (3 versions after introduction)

---

## 12. Migration plan

### 12.1 Goal statement / done criteria

**Done when all of the following hold:**

1. `from atdd.coach.core import next_transition, evaluate_evidence, review_phase_output, merge_readiness, escalation_for` succeeds without importing any I/O module (enforced by [Appendix A test](#appendix-a-import-discipline-test)).
2. `tests/lifecycle/test_full_issue_parity.py` passes in CI on every PR.
3. `tests/architecture/test_layer_imports.py` passes in CI on every PR.
4. `tests/train/test_jsonl_crash_recovery.py` passes (added at Child 9).
5. `atdd coach <N>` end-to-end uses `TrainRunner` → `coach.core` → `runtime` → `integrations` with no direct `coach.commands.coach.*` private calls.
6. Issues #840, #871, #872, #882 all closed by the migration (not separately).
7. All 13 incident defenses (I-1 through I-13) have explicit tests in `tests/incident_defenses/`.
8. CLAUDE.md no longer contains a duplicate phase machine (it loads from `phase_machine.convention.yaml`).
9. Observer is a read-only consumer with no orchestration side effects.
10. The reserved `--runner temporal` and `--runner langgraph` CLI flags exist but only `--runner jsonl` is implemented.

### 12.2 Wave plan

| Wave | Children | Concurrent agents | Wall-clock target | Key delivery |
|---|---|---|---|---|
| **A** | 1 | 1 | 0.5–1 day | Coach-core typed API + phase machine YAML frozen |
| **B** | 2, 3 | 2 | 0.5–1 day | Required-CI parity + import tests; ValidatorReport schema; persistence Protocol |
| **C** | 4, 5, 6 | **3** | 2–3 days | GitHub adapter + #882; worktree extract; **agent_control + #840/#871/#872 closure** |
| **D** | 7 | 1 | 1 day | `JsonlPersistenceStore` + `load_conventions` + `materialize_evidence` |
| **E** | 8 | 1 | 1 day | `TrainRunner` Protocol + `JsonlTrainRunner` + `_drive_single_issue` move |
| **F** | 9, 10 | **2** | 1–1.5 days | `run_wave` + `atdd resume` + crash-recovery test; spawn split + final purity sweep + observer first-class |

Max parallelism is **3 agents** (Wave C). Realistic total: **~7–9 working days; ~2 weeks calendar** with review.

**Why these groupings (dependency rationale):**

- **A → B:** B needs the types frozen in A.
- **B(2) ∥ B(3):** parity-test fixtures (2) and validator/persistence contracts (3) touch disjoint files.
- **C(4) ∥ C(5) ∥ C(6):** GitHub adapter, worktree, and agent_control share no source files and have no inter-dependency. Each depends only on Child 1 (types) + Child 2 (gates).
- **C → D:** Child 7's `materialize_evidence` calls Child 4's GitHub adapter and Child 5's worktree helpers; it must wait for both.
- **D → E:** Child 8's `JsonlTrainRunner` consumes Child 7's `PersistenceStore` and Child 6's `AgentController`.
- **E → F:** Child 9 (`run_wave` + `atdd resume`) and Child 10 (spawn split + purity sweep) both depend on Child 8's runner. They can run in parallel because Child 9 adds new code (wave_runner, resume CLI) while Child 10 cleans up old code (spawn.py split, coach.py shrink); they touch different files.

### 12.3 Per-PR requirements

Every PR in the migration MUST:

1. Keep `tests/lifecycle/test_full_issue_parity.py` green (after Child 2).
2. Keep `tests/architecture/test_layer_imports.py` green (after Child 2).
3. Enumerate in its PR description which incident defenses (I-1 to I-13) it preserves and reference the tests.
4. Introduce NO new I/O imports under `atdd.coach.core`.
5. Either add a new module under the right layer OR move an existing private function — never both in the same PR.
6. Add a compatibility shim for any moved public/semi-public symbol, marked `@deprecated(removal="3.87.0")`.
7. Update this document (`docs/coach-decomposition.md`) if any contract changes.

### 12.4 Rollback procedure

If a child PR introduces a regression after merge:

1. **First option:** land a forward-fix in the next PR (preferred — keeps the migration moving).
2. **Revert only if:** parity test breaks or production dispatch breaks for multiple users.
3. **Revert procedure:** `git revert <merge_commit>` on a `fix/<child>-revert` branch, normal PR flow, no force push.
4. **Per-child kill switch (Child 6 specifically):** `runtime.agent_control` ships with a feature flag `ATDD_USE_LEGACY_SPAWN=1` that routes back to the pre-extraction code path; defaults off but exists for at least one minor version.

---

## 13. Sequenced children (10)

Each child below is a separate GitHub issue. The body of each issue extracts its section verbatim plus an issue-body metadata header (Branch, Train, Graph Context). All children belong to umbrella issue. Acceptance criteria are testable; dependencies are absolute (do not start a child before its dependencies merge).

### Slug-vs-module-name divergence (intentional)

Children #894, #895, and #896 carry historical slugs that include `workflow` (e.g. `extract-workflow-persistence-and-events-schema`). The slugs were minted before the §3.1.1 train-native naming correction. Renaming the slugs would force re-creation of the issues + worktrees + branches, which is churn for no functional gain. The **destination modules are `atdd.train.*` per §3.1.1 and the scope sections below.** Workers MUST follow the scope (creates `src/atdd/train/...`), not the slug. The slug is a stable identifier for the work item, not a destination path.

### 13.1 Child 1 — Freeze Coach-core typed API + phase machine YAML

**Slug:** `freeze-coach-core-typed-api-and-phase-machine`
**Type:** `implementation`
**Train:** `0001-self-compliance-validate`
**Depends on:** none
**Blocks:** every other child

**Scope:**
- Create `src/atdd/coach/core/types.py` containing every type from §4.1 and §4.2.
- Create `src/atdd/coach/core/__init__.py` exposing the five pure functions from §4.3 with placeholder implementations that read from `Conventions`.
- Create `src/atdd/coach/conventions/phase_machine.convention.yaml` with the data from §4.5.
- Remove the duplicate phase machine from CLAUDE.md (the managed block will load from the YAML).
- Add table-driven unit tests for each pure function (no mocking of anything; pure inputs only).

**Out of scope:**
- Moving any existing coach.py code.
- Implementing `materialize_evidence` (that's Child 3/7).
- Any I/O.

**Acceptance:**
- `from atdd.coach.core import next_transition, evaluate_evidence, review_phase_output, merge_readiness, escalation_for` succeeds.
- Test file `tests/coach/test_core_pure.py` has ≥90% line coverage of `coach.core`.
- `python -c "import atdd.coach.core; import sys; assert 'subprocess' not in sys.modules"` passes after fresh import.
- `phase_machine.convention.yaml` is the only source of phase transitions in the repo (`grep -r 'INIT.*PLANNED' src/` returns only YAML matches).

**Closes:** none yet (sets up the rest).

---

### 13.2 Child 2 — Lifecycle parity test + import-discipline test

**Slug:** `add-lifecycle-parity-and-import-discipline-tests`
**Type:** `implementation`
**Train:** `0001-self-compliance-validate`
**Depends on:** Child 1
**Blocks:** Children 4–10 (they all need these tests green)

**Scope:**
- Create `tests/lifecycle/test_full_issue_parity.py` per §10.1.
- Create `tests/architecture/test_layer_imports.py` per Appendix A.
- Create `InMemoryPersistenceStore` fixture for the parity test.
- Create `FakeGitHub`, `FakeAgent`, `FakeObserver` fixtures.
- Create `LocalDryRunRunner` (used by the parity test as a checkpoint between full extraction).
- Wire both tests as required-CI checks in `.github/workflows/atdd-validate.yml`.

**Out of scope:**
- Actually using these fixtures elsewhere yet.

**Acceptance:**
- Both tests pass against current Coach-core (placeholder implementations from Child 1).
- Both tests are marked required-CI; failing either blocks PR merge.
- `tests/lifecycle/test_full_issue_parity.py` runs in <30s.
- `tests/architecture/test_layer_imports.py` runs in <5s.

**Closes:** none yet (gate for the rest).

---

### 13.3 Child 3 — ValidatorReport contract + persistence materialization API

**Slug:** `define-validator-report-and-persistence-materialization-contract`
**Type:** `implementation`
**Train:** `0001-self-compliance-validate`
**Depends on:** Child 1
**Blocks:** Children 7, 8

**Scope:**
- Freeze the `ValidatorReport` type (defined in §4.2; already in `atdd.coach.core.types`).
- Create `src/atdd/validators/emit.py` with `emit_reports(reports: tuple[ValidatorReport, ...]) -> None`.
- Migrate existing validators to call `emit_reports`. Either inline OR via a small adapter on `assert_disposition_satisfied`.
- Create `src/atdd/train/persistence.py` with the `PersistenceStore` Protocol (signatures only; first impl ships in Child 7).
- Specify the conventions snapshot contract: define `load_conventions(repo_root) -> Conventions` signature; first impl in Child 7.
- Specify the events.jsonl schema with `schema_version: "1.0"`; document event types from §5.2.

**Out of scope:**
- Implementing `JsonlPersistenceStore` (Child 7).
- Implementing `materialize_evidence` body (Child 7).

**Acceptance:**
- Every validator currently in the repo emits `ValidatorReport` rows (verifiable by running validators with `--collect-reports` and inspecting output).
- `PersistenceStore` Protocol has every method from §4.6.
- `from atdd.train.persistence import PersistenceStore, load_conventions` succeeds.
- Parity test still green.

**Closes:** none yet (contract for downstream).

---

### 13.4 Child 4 — Extract GitHub adapter + ship #882

**Slug:** `extract-github-integrations-and-ship-projects-v2-sync`
**Type:** `implementation`
**Train:** `0001-self-compliance-validate`
**Depends on:** Child 1, Child 2
**Blocks:** Child 7 (persistence reads via this)

**Scope:**
- Create `src/atdd/integrations/github/{issue_state,projects_v2,pr,checks}.py` per §4.10.
- Implement `projects_v2.sync_status_field()` (GraphQL mutation; requires `PROJECT_TOKEN`).
- Implement `issue_state.transition_phase()` as the atomic label+Projects-v2 swap.
- Migrate all call sites in `atdd.coach.commands.coach` and elsewhere to use the new adapter (preserve a thin compatibility shim in the old location).
- Add integration tests against gh CLI JSON fixtures (no live API).
- Document `PROJECT_TOKEN` setup in `docs/operator-projects-v2-token.md`. *(Historical — the doc no longer exists. #1051 decommissioned Projects v2; #1621 deleted the doc, which was still instructing operators to set `GH_TOKEN` to the PAT with a `||` fallback to `GITHUB_TOKEN`. `||` is a preference, not a fallback: with the secret set the PAT always won, and since the job's `permissions: issues: write` binds to `GITHUB_TOKEN` alone, every auto-phase label write failed.)*

**Out of scope:**
- Removing the old call sites (they're shimmed, removed in Child 10).

**Acceptance:**
- `atdd issue <N> --status COMPLETE` updates BOTH the label AND the Projects v2 Status field (closes #882).
- Lifecycle parity test still green.
- Each of the 4 modules (`issue_state`, `projects_v2`, `pr`, `checks`) has at least one fixture-based integration test under `tests/integrations/github/` — verifiable by `pytest tests/integrations/github/ --collect-only` listing ≥1 test per module file (≥4 total).
- The 13-incident defense table still preserved (specifically I-12: advancement before merge).

**Closes:** **#882** ("Project v2 board status-field sync gap").

---

### 13.5 Child 5 — Extract runtime.worktree

**Slug:** `extract-runtime-worktree-preserving-incident-defenses`
**Type:** `implementation`
**Train:** `0001-self-compliance-validate`
**Depends on:** Child 1, Child 2
**Blocks:** Child 7 (train runner uses worktree)

**Scope:**
- Create `src/atdd/runtime/worktree.py` with `ensure_issue_worktree`, `remove_worktree`, branch safety helpers.
- Preserve incident defenses I-1, I-2, I-9 with explicit tests in `tests/incident_defenses/test_worktree_safety.py`.
- Migrate call sites in `atdd.coach.commands.coach`, `atdd.coach.commands.branch`, `atdd.coach.commands.issue_lifecycle` to use the new module (shim originals).
- `ensure_issue_worktree` MUST set `git config --worktree core.bare false` on every new worktree (I-9).

**Out of scope:**
- Anything involving spawn or agent control.

**Acceptance:**
- Creating a new worktree via `atdd issue <slug>` produces a worktree with `core.bare=false` per-worktree override.
- Parity test still green.
- All three incident defense tests pass.
- No new worktree creation path exists outside `runtime.worktree`.

**Closes:** none yet (cleanups the surface).

---

### 13.6 Child 6 — Extract runtime.agent_control + close #840/#871/#872

> **SUPERSEDED — pruned from core by #1480.** Core coach is lifecycle
> governance and does not manage sub-workers, so this layer was removed
> outright rather than relocated to a provider. The specification below is
> retained as the design record of what once shipped; it describes no
> current core module.

**Slug:** `extract-runtime-agent-control-and-close-spawn-cluster`
**Type:** `implementation`
**Train:** `0001-self-compliance-validate`
**Depends on:** Child 1, Child 2
**Blocks:** Child 10
**RISK:** **XL — biggest blast radius in the migration**

**Scope:**
- Create `src/atdd/runtime/agent_control.py` with `AgentController` Protocol, `DispatchSpec`, `ReadyResult`, `AgentEvent`, `AgentSignal`, `AgentHandle` per §4.8.
- Implement `CmuxAgentController` (default, #978/#979): cmux-native launch — the agent's positional prompt seeds AND auto-submits the first turn; decisions ride the cmux Feed hooks.
- Implement `HeadlessPrintController`: `claude -p` for non-interactive use.
- Create `src/atdd/runtime/multiplexer.py` with the view-only `Multiplexer` Protocol (§4.9). Strip all control methods (`paste_text`, `send_key`, `capture_pane_text`) — they MUST NOT exist on the Protocol surface.
- Migrate `atdd.coach.commands.spawn` to dispatch through `CmuxAgentController` by default.
- Add `runtime.agent_control` tests for the cmux-native launch shape.

**Out of scope:**
- The actual train runner (Child 8).

**Acceptance:**
- `atdd coach <N>` boots via cli-return transport by default; **no `paste-landed` errors** in a 100-iteration stress test.
- A test asserts the prompt primed via `cli-return.jsonl` is observable in the agent's TUI within 5s of spawn (closes #872).
- A test asserts a stdin INTERRUPT signal terminates the wrapped agent (closes #871).
- `ATDD_USE_LEGACY_SPAWN=1` falls back to the pre-extraction path (kill switch).
- Import-discipline test confirms `Multiplexer` has no control methods.
- Parity test still green.

**Closes:** **#871** (stdin gap), **#872** (submit gap), **#840** (structurally — cli-return is the default control plane; TUI scrape deprecated).

---

### 13.7 Child 7 — Extract train.persistence + events schema

**Slug:** `extract-workflow-persistence-and-events-schema`
**Type:** `implementation`
**Train:** `0001-self-compliance-validate`
**Depends on:** Child 3 (PersistenceStore Protocol + ValidatorReport), Child 4 (GitHub adapter), Child 5 (runtime.worktree)
**Blocks:** Child 8
**Wave:** D (sequential after Wave C lands)

**Scope:**
- Implement `JsonlPersistenceStore` (per §4.6 protocol).
- Implement `load_conventions(repo_root) -> Conventions` with snapshot+hash.
- Implement `materialize_evidence(issue_number) -> Evidence` aggregating manifest + GitHub adapter (from Child 4) + validator reports (from Child 3) + filesystem artifacts.
- Implement event log: append `RunStarted` with `conventions_hash` and `conventions_snapshot_ref`; write conventions.snapshot.yaml on run create.
- Add replay determinism test: same `(events.jsonl, conventions.snapshot.yaml)` → same decisions.

**Out of scope:**
- The runner itself (Child 8).

**Acceptance:**
- `JsonlPersistenceStore` implements every `PersistenceStore` method.
- Creating a run writes `runs/<id>/conventions.snapshot.yaml` and a matching `conventions.hash`.
- Replay test passes: pickle a `JsonlPersistenceStore` mid-loop, recreate it, replay produces identical decisions.
- Parity test still green.

**Closes:** none yet.

---

### 13.8 Child 8 — Extract train.issue_runner + TrainRunner protocol

**Slug:** `extract-workflow-issue-runner-and-workflow-runner-protocol`
**Type:** `implementation`
**Train:** `0001-self-compliance-validate`
**Depends on:** Child 6, Child 7
**Blocks:** Child 9

**Scope:**
- Create `src/atdd/train/runner_iface.py` with `TrainRunner` Protocol and `PolicyHandle` per §4.7.
- Implement `JsonlTrainRunner.start_issue`, `handle_event`, `status`, `cancel`.
- Move from `coach.py`: `_drive_single_issue` (main entry), `_process_watcher_events`, `_process_injected_events`, `_make_resume_transition_action`. The old function names remain as `@deprecated` compatibility shims that call into the new runner.
- Wire `atdd coach <N>` CLI to instantiate `JsonlTrainRunner` + `PolicyHandle` and call `start_issue`.
- Reserve `--runner temporal` and `--runner langgraph` CLI flags (raise `NotImplementedError("see docs/coach-decomposition.md §7.2/§7.3")`).
- Reserve `train.runner` config key.

**Out of scope:**
- `run_wave` and `resume` (Child 9).

**Acceptance:**
- `atdd coach <N>` end-to-end runs via `TrainRunner` — no direct `coach.commands.coach.*` private calls remain.
- Adding a new event type requires only an `events.jsonl` schema bump; no Coach-core change.
- Parity test still green.

**Closes:** none yet.

---

### 13.9 Child 9 — Extract train.wave_runner + `atdd resume` CLI

**Slug:** `extract-workflow-wave-runner-and-atdd-resume-cli`
**Type:** `implementation`
**Train:** `0001-self-compliance-validate`
**Depends on:** Child 8
**Blocks:** Child 10

**Scope:**
- Implement `JsonlTrainRunner.run_wave` with `train.concurrency.max_parallel_issues` config.
- Move from `coach.py`: `_resolve_waves`, `_drive_wave_concurrently`, `_execute_cold_start`.
- Implement `JsonlTrainRunner.resume(run_id)` per §6.3.
- Add `atdd resume <run_id>` CLI command (new public surface).
- Add `tests/train/test_jsonl_crash_recovery.py` per §10.3 — gate test for any future Temporal adoption.

**Out of scope:**
- Spawn split (Child 10).

**Acceptance:**
- `atdd coach 816 880 884` runs three issues concurrently per the concurrency limit.
- Crash-recovery test: `kill -9` mid-wave + `atdd resume <run_id>` → identical decisions.
- Parity test still green.
- `atdd resume --help` documents the new command.

**Closes:** none yet.

---

### 13.10 Child 10 — Spawn split + final purity sweep

**Slug:** `split-spawn-and-final-purity-sweep`
**Type:** `implementation`
**Train:** `0001-self-compliance-validate`
**Depends on:** Child 6, Child 8
**Blocks:** none (closes the migration)

**Scope:**
- Split `atdd.coach.commands.spawn`:
  - Coach keeps: persona/prompt-template mapping (already in Coach-core types).
  - Runtime takes: `cmd_spawn` (now thin), retry/backoff, materialization check, surface attachment, observer wiring.
- Remove all remaining direct subprocess/gh/cmux references from `atdd.coach.core` (final purity sweep).
- Promote `atdd.observer` to a first-class read-only consumer per §8. Remove observer-launch side effects from `coach.py`.
- Remove the duplicate phase machine references that any earlier child left behind.
- Remove compatibility shims that have been marked deprecated for ≥3 minor versions.

**Out of scope:**
- Anything not strictly cleanup.

**Acceptance:**
- `tests/architecture/test_layer_imports.py` passes with the strictest version: no forbidden imports anywhere in `atdd.coach.core`.
- `atdd observer` runs without ever writing to events.jsonl or output.log (file-watcher only).
- `atdd.coach.commands.coach`: structural slim **deferred to follow-up** — see §21 (Children 7-9 introduced train↔coach module-level coupling + ~20 monkeypatch-bound tests that block in-PR re-architecture without risking the parity/import-discipline gates). What this PR DOES deliver under the "final purity sweep" banner: `coach.core` verified pure (A1), `atdd.observer` first-class read-only (A2), parity green (A4), incident-defenses I-1..I-13 explicit (A5).
- Parity test still green.
- All 13 incident defenses (I-1 through I-13) have explicit tests in `tests/incident_defenses/`.

**Closes:** the migration. Mark the umbrella issue COMPLETE.

#### Closing-child realization note (#897, 2026-05-31)

The closing PR delivers the **architectural** acceptance in full and defers the
two **mechanical-LOC-reduction** items to a tracked follow-up (operator-approved
2026-05-31). What landed vs. what moved out:

**Delivered and gate-green:**
- Final purity sweep — `atdd.coach.core` carries zero forbidden imports; the
  strictest `tests/architecture/test_layer_imports.py` (incl.
  `test_coach_core_has_no_io_at_import_time`) is green. `coach.core` is two pure
  files (`types.py`, `__init__.py`).
- `atdd.observer` promoted to a first-class **read-only** consumer (§8) — opens
  `events.jsonl` / `output.log` in read mode only; proven by a runtime
  `open()`-guard, a static AST no-write test, and byte-identical-after-view
  assertions. Singleton lifecycle (I-6) enforced. `atdd observer view` surfaces
  the aggregated stream.
- **All 13 incident defenses (I-1 … I-13)** have explicit tests in
  `tests/incident_defenses/` (worktree trio + the consolidated suite).
- Lifecycle parity test stays green.

**Deferred to follow-up (tracked, see §21):**
- Reducing `atdd.coach.commands.coach` to ≤300 LOC and splitting
  `coach.commands.spawn` into a runtime-owned `cmd_spawn`.
- **Why deferred (structural):** Children 7–9 wired `atdd.train.issue_runner` to
  import `atdd.coach.commands.coach` at module level and call its orchestration
  helpers through the `_coach.<name>` *module object* (a deliberate seam so the
  ~20 tests that `monkeypatch.setattr(coach, "_helper", …)` keep intercepting).
  The helpers also close over coach-local session types (`Config`,
  `StateMachine`, `CoachContext`). Hitting ≤300 means relocating those helpers
  **and** the session types into the train layer, inverting that seam, and
  migrating the coupled tests — a cross-cutting re-architecture whose blast
  radius reaches the non-negotiable parity + import-discipline gates (§20.3). It
  is genuinely separable cleanup, not part of the "purity" guarantee (the CLI
  shell is *permitted* I/O; only `coach.core` must be pure), so it is safer as a
  dedicated PR than rushed into the closing migration PR.

The umbrella's architectural goals (pure core, extracted layers, incident
defenses, first-class observer, green gates) are met by this PR; the residual is
mechanical LOC reduction.

---

## 14. Effort estimate

| Wave | Children | Concurrent agents | Realistic wall-clock |
|---|---|---|---|
| A | 1 | 1 | 1 day |
| B | 2, 3 | 2 | 1 day |
| C | 4, 5, 6 | **3** | 2–3 days (agent_control is the bottleneck) |
| D | 7 | 1 | 1 day |
| E | 8 | 1 | 1 day |
| F | 9, 10 | 2 | 1–1.5 days |
| **Total** | 10 | **max 3** | **~7–9 working days; ~2 weeks calendar** |

Total LOC: ~15–25k (40–50% tests).

---

## 15. Gradual benefit map

| After wave | Immediate benefit |
|---|---|
| **A** | Coach decision logic table-testable in 30ms. Phase machine is data. |
| **B** | Required-CI parity + import gates protect every subsequent PR. Validators emit uniform reports → observer output improves today. |
| **C** | **`atdd coach` becomes reliable**: cli-return is default, paste-landed is gone, Project v2 board syncs. The 4 most painful operator issues (#840/#871/#872/#882) all close. Worktree + GitHub adapters reusable from other commands. |
| **D** | `TrainRunner` seam exists; ready for Temporal/LangGraph if/when needed. Coach.py visibly smaller. |
| **E** | `atdd resume <run_id>` ships. Crashes become recoverable. Waves are properly isolated. |
| **F** | Final architecture realized. Observer first-class. Coach-core verifiably pure. Ready to plug in Temporal/LangGraph behind the seam. |

Highest-leverage waves for operator experience: **B** and **C**. After Wave C alone, the system is dramatically more reliable even if D–F slip.

---

## 16. Risks and mitigations

| # | Risk | Mitigation |
|---|---|---|
| R-1 | Coach.py interconnection surfaces hidden coupling per extraction | Each child PR may need a precursor "untangle" commit; budget +20-30% per child |
| R-2 | Validator refactor scope (Child 3) is wider than expected | If discovered during Child 1 audit, split Child 3 into 3a (schema) + 3b (migrate validators) |
| R-3 | Existing tests mock coach.py internals | Each child must refactor or rewrite breaking tests as part of its scope |
| R-4 | Child 6 (agent_control) breaks dispatch for all users | Ships with `ATDD_USE_LEGACY_SPAWN=1` feature flag; soak for one minor version before removing legacy path |
| R-5 | Tooling friction (core.bare bleeds, GitHub board gaps, lifecycle validator misalignment) hits during migration | Workers route around with `atdd emergency` or fix in-place; document each incident in the relevant child PR |
| R-6 | Migration's own dogfood loop surfaces new bugs | Treat as signal — file as separate issues; do not let them block the migration |
| R-7 | Two equally-maintained runners (JSONL + Temporal) emerge | JSONL is canonical until Temporal earns its weight via §10.3 crash-recovery test failure; no Temporal code until then |
| R-8 | Convention YAML divergence between source files and snapshot | Snapshot is the single source of truth for an in-flight run; sources are read only at run start; documented in §4.4 |
| R-9 | Operator confused by reserved-but-unimplemented `--runner temporal` flag | CLI raises `NotImplementedError` with a clear message pointing to this doc's §7.2 |
| R-10 | Compatibility shims accumulate and become permanent | Auto-PR at the removal target version; CI warns on shim use; documented removal cadence |

---

## 17. Glossary

| Term | Meaning |
|---|---|
| **Coach-core** | The pure-policy module `atdd.coach.core`; no I/O |
| **Train** | The domain route a Coach drives an issue along: phase machine, WMBT / claim dependency graph, acceptance path, evidence requirements, persona/prompt mapping. Data/policy input, **not** an execution engine. (Per §3.1.1.) |
| **TrainRunner** | The stateful execution layer (`atdd.train.*`). Creates runs, materializes evidence, records events, dispatches agents, waits, resumes, runs waves, calls runtime/integration adapters. **This** is the Temporal/LangGraph-equivalent — not Train. (Per §3.1.1.) |
| **Runtime** | Execution layer (worktree, multiplexer, agent_control) |
| **Integrations** | External-system adapters (GitHub) |
| **Validators** | Test-shaped checks that emit `ValidatorReport` |
| **DispatchSpec** | Typed handoff from train runner to runtime to spawn a worker |
| **PolicyHandle** | Frozen bundle of (coach_module, conventions) passed to the runner |
| **Evidence** | Frozen snapshot of everything Coach needs to decide |
| **Verdict** | Coach's decision (PROCEED/STAY/BLOCKED/ESCALATE) with rule references |
| **Conventions snapshot** | Frozen conventions YAML for a single run; guarantees replay determinism |
| **events.jsonl** | Single-writer (train runner) append-only event log |
| **cli-return.jsonl** | Correction inbox the worker drains to receive mid-run corrections |
| **output.log** | tee'd output from a wrapped agent; observer reads it |
| **Run** | One execution of `TrainRunner.start_issue`; identified by `run_id` |
| **Wave** | A batch of issues run concurrently |
| **Incident defense** | A specific behavior in the current code that prevents a past incident; numbered I-1 through I-13 in §9 |
| **Parity test** | The end-to-end test in `tests/lifecycle/test_full_issue_parity.py` that gates every PR |
| **Import-discipline test** | The architectural test in `tests/architecture/test_layer_imports.py` that enforces §3.3 |

---

## 18. Appendix

### Appendix A — Import-discipline test (full code)

```python
# tests/architecture/test_layer_imports.py
import ast
import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"

FORBIDDEN_BY_LAYER = {
    "atdd.coach.core": {
        "subprocess", "os.system", "requests", "urllib.request", "urllib3",
        "git", "gh", "cmux", "threading", "multiprocessing", "asyncio",
        "atdd.runtime", "atdd.integrations", "atdd.train", "atdd.observer",
    },
    "atdd.train": {
        "atdd.cli", "atdd.observer",
    },
    "atdd.runtime.worktree": {
        "atdd.coach", "atdd.train", "atdd.integrations",
        "atdd.runtime.agent_control", "atdd.runtime.multiplexer",
    },
    "atdd.runtime.multiplexer": {
        "atdd.coach", "atdd.train", "atdd.integrations",
        "atdd.runtime.agent_control",
    },
    "atdd.runtime.agent_control": {
        "atdd.coach", "atdd.train", "atdd.integrations",
        "atdd.runtime.multiplexer",
    },
    "atdd.integrations.github": {
        "atdd.coach", "atdd.train", "atdd.runtime",
    },
}

def _module_imports(py_file: Path) -> set[str]:
    tree = ast.parse(py_file.read_text())
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                imports.add(n.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
    return imports

def _layer_files(layer: str) -> list[Path]:
    layer_dir = SRC / layer.replace(".", "/")
    if not layer_dir.is_dir():
        return []
    return [p for p in layer_dir.rglob("*.py")
            if "/tests/" not in str(p) and not p.name.startswith("test_")]

@pytest.mark.parametrize("layer", sorted(FORBIDDEN_BY_LAYER.keys()))
def test_layer_has_no_forbidden_imports(layer: str):
    forbidden = FORBIDDEN_BY_LAYER[layer]
    violations = []
    for py in _layer_files(layer):
        for imp in _module_imports(py):
            for fb in forbidden:
                if imp == fb or imp.startswith(fb + "."):
                    violations.append((py, imp, fb))
    assert not violations, "\n".join(
        f"{p.relative_to(REPO_ROOT)} imports {imp!r} (forbidden: {fb})"
        for p, imp, fb in violations
    )

def test_coach_core_has_no_io_at_import_time():
    """Sanity: importing coach.core fresh must not pull subprocess into sys.modules."""
    for mod_name in list(sys.modules):
        if mod_name.startswith("atdd"):
            del sys.modules[mod_name]
    import atdd.coach.core  # noqa: F401
    assert "subprocess" not in sys.modules, "atdd.coach.core leaked subprocess at import"

def test_multiplexer_protocol_has_no_control_methods():
    from atdd.runtime.multiplexer import Multiplexer
    forbidden = {"paste_text", "send_key", "capture_pane_text"}
    methods = {name for name in dir(Multiplexer) if not name.startswith("_")}
    leaked = forbidden & methods
    assert not leaked, f"Multiplexer Protocol leaked control methods: {leaked}"
```

### Appendix B — Lifecycle parity test (full code)

```python
# tests/lifecycle/test_full_issue_parity.py
import pytest
from atdd.coach.core.types import Phase, IssueType, PolicyHandle
from atdd.train.runners.jsonl import JsonlTrainRunner
from atdd.train.persistence import InMemoryPersistenceStore, load_conventions
from atdd.coach import core as coach_core
from tests.fixtures import FakeGitHub, FakeAgent, FakeObserver, tmp_repo

@pytest.mark.parity
def test_full_lifecycle_init_to_complete(tmp_repo, fake_github, fake_agent):
    persistence = InMemoryPersistenceStore()
    conventions = load_conventions(tmp_repo)
    policy = PolicyHandle(coach_module=coach_core, conventions=conventions)
    runner = JsonlTrainRunner(persistence=persistence,
                                 github=fake_github,
                                 agent=fake_agent)

    issue = fake_github.create_issue(slug="parity", type=IssueType.IMPLEMENTATION)
    run_id = runner.start_issue(issue.number, policy=policy)

    expected_phases = [Phase.PLANNED, Phase.RED, Phase.GREEN,
                       Phase.SMOKE, Phase.REFACTOR, Phase.COMPLETE]
    for expected in expected_phases:
        fake_agent.signal_phase_done(issue.number)
        runner.handle_event(run_id, _tick())
        assert runner.status(run_id).current_phase == expected

    assert fake_github.pr_for(issue.number).state == "MERGED"
    assert "atdd:COMPLETE" in fake_github.issue(issue.number).labels
    assert fake_github.project_v2_status(issue.number) == "COMPLETE"

    # Replay determinism
    replay_persistence = InMemoryPersistenceStore.from_events(
        persistence.replay_events(run_id))
    replay_runner = JsonlTrainRunner(persistence=replay_persistence,
                                        github=fake_github,
                                        agent=fake_agent)
    replay_runner.resume(run_id)
    assert (list(persistence.decisions(run_id)) ==
            list(replay_persistence.decisions(run_id)))
```

### Appendix C — Phase machine YAML (canonical)

See §4.5. Single source: `src/atdd/coach/conventions/phase_machine.convention.yaml`.

---

---

## 19. Coach operating manual

This section tells the **operator (acting as coach)** how to run the project across waves. Workers do the implementation; the coach orchestrates, gates, and reviews.

### 19.1 The coach's job in one sentence

**Gate wave starts, enforce per-PR requirements, surface BLOCKED/ESCALATE, and update this doc when reality requires it.**

### 19.2 Pre-flight before starting any wave

| Check | Command | Pass condition |
|---|---|---|
| All previous-wave children CLOSED | `gh issue view 887 --json body` (read child status table) | All listed as CLOSED |
| Lifecycle parity test green on main | `gh run list --branch main --workflow=238935543 --limit=1` (after #889) | conclusion: success |
| Import-discipline test green on main | same run, check `test_layer_imports.py` step (after #889) | conclusion: success |
| Crash-recovery test green on main | same run, check `test_jsonl_crash_recovery.py` step (after #896) | conclusion: success |
| No stale phantom worktrees | `git worktree list` cross-referenced against open issues | no orphan dirs |
| `core.bare=false` on shared config | `git config --file <main>/.git/config core.bare` | `false` |
| `atdd` on PATH is current version | `atdd --version` | matches `pyproject.toml::version` on origin/main |

If any check fails, halt the wave. Address the root cause; do not start workers on broken substrate.

### 19.3 Per-child PR review checklist

When a child worker opens a PR, the coach MUST verify ALL of:

- [ ] Lifecycle parity test passes (after #889).
- [ ] Import-discipline test passes (after #889).
- [ ] PR description enumerates which incident defenses (§9, I-1 to I-13) it preserves and references the test.
- [ ] No new I/O imports under `atdd.coach.core` (the import-discipline test confirms; reviewer SHOULD spot-check anyway).
- [ ] Compatibility shim added for any moved public/semi-public symbol, marked `@deprecated(removal="3.87.0")`.
- [ ] Doc updated if any contract changed (this file). If yes, the change must be coherent with downstream child specs.
- [ ] PR diff scope matches the child's "Scope" section — no scope creep into another child's territory.
- [ ] CI green on the PR head commit (all checks SUCCESS).

Reject PRs that fail any of these. Forward-fix is preferred over revert when possible.

### 19.4 Wave gating rules

| Trigger | Coach action |
|---|---|
| All children of wave N CLOSED | Verify pre-flight (§19.2) → green-light wave N+1 |
| One child of wave N still IN-FLIGHT >2× estimate | Investigate: blocker, scope drift, or under-estimated? Update §14 if estimate was wrong |
| Child enters BLOCKED phase | Read `RunBlocked` event from the child's run dir → address the gap → `atdd resume <run_id>` |
| Child enters ESCALATED phase | Halt the run. Operator MUST decide: address the underlying cause (e.g., contradictory conventions) or revise the umbrella scope |
| Parity test breaks for >24h | Halt next-wave starts; root-cause and forward-fix or revert |

### 19.5 When to update this document (and when NOT to)

**Update the doc when:**
- A typed contract genuinely needs to change (e.g., adding a field to `Evidence`)
- A child discovers the spec is wrong or incomplete
- A new incident defense is uncovered (add to §9 table)
- The wave plan needs revision (e.g., a child is too large and must be split)
- The compatibility deprecation timeline shifts

**Do NOT update the doc when:**
- A worker takes a path the doc allows but didn't explicitly bless — that's normal latitude
- An implementation detail differs from a doc example (the example is illustrative)
- Bug-fixes inside a layer (those go in commit messages and tests)

**How to update:** doc change lands in the SAME PR as the implementation change that requires it. PR description MUST state "doc updated: §X.Y because Z."

### 19.6 Escalation triggers (operator must intervene beyond coach)

| Trigger | Why operator-only |
|---|---|
| Two children blocked on the same incident-defense gap | Indicates §9 is incomplete; needs human judgement on remediation |
| Compatibility shim removal date hit but consumers still exist | Risk of breaking downstream; needs explicit operator decision |
| Request to add a new phase / persona / runner backend | Changes the umbrella's scope; needs explicit ratification |
| Production dispatch broken for multiple users for >2h | Revert decision; needs operator authority |
| Convention YAML divergence between two source files | Could change live decisions; needs human reconciliation |

### 19.7 Cross-session continuity duties

When ending a session, the coach SHOULD:

1. Update memory with a session-end snapshot (which child is at which phase, any unresolved blockers).
2. Ensure any uncommitted spec changes are on a branch (not just in working tree).
3. Note any operational gotchas encountered (e.g., `core.bare` bleed) that future sessions need to know.
4. Close any cmux surfaces / kill any zombie processes from this session.

---

## 20. Session handoff protocol

This section tells a **new agent starting a fresh session** how to inherit the coach role without losing continuity. The user will signal a handoff by referencing this document, the umbrella #887, or any child #888–#897, or by saying things like "continue the decomposition" or "where are we on the coach split."

### 20.1 Bootstrap — MUST do before any action

Run these in order. Do not skip. Do not parallelize with anything else.

```bash
# 1. Read the source of truth end-to-end.
#    Path: docs/coach-decomposition.md (this file)
#    Time: ~10-15 min careful read. NO skipping. NO skim.

# 2. Read the umbrella's current state.
gh issue view 887

# 3. Inspect all 10 children's current phases.
for n in 888 889 890 891 892 893 894 895 896 897; do
  gh issue view $n --json number,state,labels --jq '"#\(.number) \(.state) \([.labels[].name])"'
done

# 4. Inspect active worktrees.
git worktree list

# 5. Inspect what's landed on main recently.
git log origin/main --oneline -20

# 6. Verify gating tests are green on main.
gh run list --branch main --workflow=238935543 --limit=3

# 7. Read auto-memory entries (the harness loads MEMORY.md automatically;
#    look specifically for: coach-decomposition-project, coach-decomposition-session-handoff,
#    and any session-end snapshots).
```

After bootstrap, the new agent SHOULD have a complete picture: what's done, what's in flight, what's blocked, where we are in the wave plan.

### 20.2 First message to the operator

The new agent's first user-facing message after bootstrap MUST:

1. **Confirm** the bootstrap completed (cite which children are in which phase).
2. **State** the current wave and the gate condition for advancing.
3. **Propose** the next action (start wave N, review a PR, address a blocker).
4. **Wait** for operator authorization before taking any action with blast radius.

Example: *"Bootstrap done. State: Wave A done (#888 CLOSED, merged 2 days ago). Wave B in flight: #889 at GREEN with PR #X open, #890 at PLANNED. No active blockers. Next action: review PR #X. Should I proceed with the review checklist, or is there something else you need first?"*

### 20.3 Invariants that survive every session boundary

These are non-negotiable. A new coach session MUST NOT relax them.

| Invariant | Why |
|---|---|
| The 10-child sequencing (888 → 897) is FIXED | Dependencies are real; reordering breaks downstream |
| The 7-layer dependency rules (§3.3) are non-negotiable | Architectural coherence depends on them |
| The parity test (§10.1) is required-CI from #889 onward; NEVER skip | Catches behavior drift; without it the migration silently breaks |
| The import-discipline test (§10.2) is required-CI from #889 onward; NEVER skip | Catches Coach-core purity violations |
| The doc is the source of truth | If reality and doc disagree, update one or the other in a single PR; never let them coexist out-of-sync |
| Phase machine lives in YAML (§4.5); NEVER hard-code transitions in Python | Adding a phase = YAML edit, not code change |
| `core.bare=false` per-worktree on every new worktree (I-9) | Prevents the recurring contamination class |
| `--worktree` flag for ANY `git config core.*` write | See #884; prevents shared-config bleed |
| Use `atdd issue`/`atdd pr`, never `gh issue create`/`gh pr create` | Conventions enforce this; ignoring breaks the manifest |

### 20.4 Handoff data the new session can rely on

The following artifacts are stable and survive across sessions:

| Artifact | Location | Updated by |
|---|---|---|
| **This document** | `docs/coach-decomposition.md` on the umbrella's branch (lands on main via #887's PR) | Coach (operator) + any child PR that changes a contract |
| **Umbrella body** | `gh issue view 887` | Coach (operator) when wave state changes |
| **Child bodies** | `gh issue view 888..897` | Coach at filing; updated only if scope genuinely changes |
| **Per-run events** | `.atdd/runtime/runs/<run_id>/events.jsonl` (after #894) | TrainRunner (single-writer) |
| **Conventions snapshot** | `.atdd/runtime/runs/<run_id>/conventions.snapshot.yaml` (after #894) | TrainRunner at run start |
| **Manifest** | `.atdd/manifest.yaml` | `atdd issue` and child PRs |
| **Auto-memory** | `/Users/alecfokapu/.claude/projects/-Users-alecfokapu-Github-atdd/memory/` | Session-end snapshots + project/reference entries |
| **Git log on main** | `git log origin/main` | Merged PRs only |

### 20.5 What the new session is NOT allowed to do without operator approval

- Reorder children
- Drop or weaken any of the per-PR requirements
- Add Temporal or LangGraph implementations (deferred per §7.2/§7.3)
- Pick a different default runner than `jsonl`
- Skip the parity test or import-discipline test
- Edit shared `.git/config` core.* without `--worktree`
- Force-push to main
- Merge a PR without verifying §19.3 checklist
- Modify the doc's contracts (§4) without operator confirmation

### 20.6 Sustainability — keeping the system coherent over time

The decomposition itself is a one-time project. The **patterns** it establishes are forever. After the migration lands:

- **Future architectural changes** SHOULD follow this same pattern: umbrella issue + spec doc in `docs/architecture/` + child issues per layer + lifecycle parity test.
- **New layers** (e.g., `atdd.integrations.gitlab`) inherit the dependency rules in §3.3.
- **New phases** are YAML edits to `phase_machine.convention.yaml`; the existing tests catch hard-coded transitions.
- **New incident defenses** add a row to §9's table + a test under `tests/incident_defenses/`.
- **The doc itself** evolves with `docs/coach-decomposition-v2.md` when the next architectural shift comes; never delete v1 (it's the historical record of why we did things this way).

---

## 21. Follow-up tasks (out of scope for the migration)

Tracked work items that surface DURING the decomposition but are explicitly **NOT in scope for any child** (#888–#897). These exist to keep child PR scope clean (§12.3 requirement 5) while still preserving the finding. Each row links to a GitHub issue that owns the follow-up.

| Item | Issue | Why deferred | Suggested timing |
|---|---|---|---|
| Pre-existing **484** broken URN refs reported by `atdd repo broken` (verified 2026-05-31 post-Wave-C; the original #905 file used the worker's "~467" estimate, which was off) | [#905](https://github.com/afokapu/atdd/issues/905) (subsumes closed [#817](https://github.com/afokapu/atdd/issues/817), whose work shipped via merged [PR #823](https://github.com/afokapu/atdd/pull/823)) | Surfaced during #893 (Child 6); not introduced by any child. Some refs are "decomposition-deferred" (resolve when later children ship their target layers), others are orthogonal. Fixing in any child PR would breach §12.3 single-thing rule and create scope creep. | After Wave F (#897) merges — at that point the "decomposition-deferred" bucket should be empty; remaining orthogonal refs get one cleanup PR (or a small set). |
| Post-commit blast-radius hook poisons shared `.git/config` → **phantom mass-deletions**. When `git commit` fires `.atdd/hooks/post-commit` → `atdd validate coach`, some validator path writes `core.bare=true` without `--worktree`, which lands in shared `main/.git/config`. The next `git status` sees the worktree as bare and stages **~2097 phantom deletions**. Workers and coach have been bypassing every commit this session via `CI=true git commit` (the hook's documented escape), making the post-commit blast-radius validators a **no-op for every wave** — so the fast-feedback loop they exist for (catch a coder violation in 30s post-commit, not 3min in CI) has been dormant. | [#884](https://github.com/afokapu/atdd/issues/884) — canonical fix: PATH-shim on `git` (`.atdd/bin/git`) blocks unscoped `core.bare`/`core.worktree`/`core.hooksPath` writes for ANY agent + adds CI validator + session-bootstrap self-heal. Complements the merged pre-push guard from #629 and the docs convention from #634. | The trigger vector (`atdd validate coach` running inside the post-commit hook) lives on the existing coach surface; #884's PATH-shim addresses it at a deeper layer than any decomposition child touches. Patching the symptom in a decomposition child PR would breach §12.3 single-thing scope. | After Wave F (#897) merges, OR sooner if #884's PATH-shim ships independently — it is not gated by the decomposition. Once #884 lands, the post-commit hook can stop being bypassed and the blast-radius loop comes back online. |

| `coach.py` thin-shell slim + spawn split (the §13.10 **A3** acceptance: reduce `atdd.coach.commands.coach` to ≤300 LOC + move `cmd_spawn` mechanics into `atdd.runtime`) | [#914](https://github.com/afokapu/atdd/issues/914) | Deferred from #897 per §20.3 (reality-vs-doc). Blocked structurally by Children 7-9 coupling: `train.issue_runner` imports `coach` at module level and calls helpers via the `_coach.<name>` module object, a seam ~20 monkeypatch-bound tests depend on; helpers also close over coach-local session types (`Config`/`StateMachine`/`CoachContext`). Slimming = relocate helpers + session types to the train layer + migrate the coupled tests — blast radius reaches the never-skip parity/import-discipline gates, so it is unsafe to rush into the closing migration PR. It is mechanical LOC reduction, NOT a purity guarantee (the CLI shell is permitted I/O; only `coach.core` must be pure, which #897 verified). | A dedicated refactor PR after #897 merges, respecting the three never-skip gates; pure refactor, no behavior change. |
| **PATH-shim layer gap** — `atdd validate` (Python process) bypasses [#884](https://github.com/afokapu/atdd/issues/884)'s PATH-shim because it makes git-config writes via in-process Python libs rather than through the user's shell PATH where `.atdd/bin/git` lives. During PR [#913](https://github.com/afokapu/atdd/pull/913)'s rebase to bring in [#884](https://github.com/afokapu/atdd/issues/884), this triggered the phantom mass-deletion symptom mid-rebase (the very thing #884 was designed to prevent). Worker recovered with `git -c core.hooksPath=/dev/null rebase origin/main`. The shell-layer defense ships and works for shell agents; the Python-layer defense is missing. | [#917](https://github.com/afokapu/atdd/issues/917) | Surfaced during Wave F (#896 rebase). Fix requires audit of all `git config core.…` / gitpython call sites under `src/atdd/**`, centralizing through a `set_scoped(key, value, scope=…)` helper that enforces `--worktree` for danger keys, plus a runtime canary at the end of every `atdd validate` invocation. Out of scope for the closing migration PR; not a regression. | After [#916](https://github.com/afokapu/atdd/issues/916) (release toolkit) lands; can be co-scheduled or after — neither blocks the other. |
| **`atdd.release` versioning toolkit missing** — `afokapu/atdd`'s `.github/workflows/post-merge-lifecycle.yml` is repo-bespoke and not toolkit-shipped, so consumer repos that adopt ATDD via `atdd init` do not receive the release hygiene. The bespoke workflow's auto-bump step requires direct push to `main`, conflicting with branch protection (the I-2 "no protected-main commit" defense). Tonight's incident: PR [#913](https://github.com/afokapu/atdd/pull/913) lifecycle failed with `GH006: Protected branch update failed` after `PROJECT_TOKEN` was added — bypassing branch protection would have regressed I-2. Path-B workaround: manual `pyproject.toml` version bump landed in [#915](https://github.com/afokapu/atdd/pull/915) (3.85.0 → 3.86.0). | [#916](https://github.com/afokapu/atdd/issues/916) | Should be a toolkit-shipped primitive (library + CLI `atdd bump` + convention + validator + workflow template) so consumers get the same release hygiene via `atdd init`. Out of scope for any decomposition child; surfaced as the lifecycle conflict. | After Wave F closes (now). Convention + validator + CLI surface before the workflow-template migration. Closure unblocks deleting `afokapu/atdd`'s bespoke `post-merge-lifecycle.yml` and the `PROJECT_TOKEN` secret. |

**Convention for adding new rows:** when a worker surfaces a substrate/repo-wide finding that's pre-existing AND would breach §12.3 if fixed inline, the coach files a tracking issue (labelled `tracking`) and appends a row to this table in the same coach-side PR. Worker references the row from their PR body under a `## Substrate / pre-existing findings` section. After-migration follow-up PRs reference the row to confirm closure.

---

**END OF SOURCE OF TRUTH**

_This document is owned by the operator (acting as coach). Worker agents executing child issues MUST read this document before starting and MUST update it (in the same PR) if any contract or schema changes during implementation. New coach sessions MUST follow the §20 handoff protocol before taking any action._
