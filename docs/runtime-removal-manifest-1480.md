# Removal manifest — #1480 (prune the relocated cmux runtime; no provider delegation)

> **Supersedes the Phase 1 manifest of 2026-07-13.** That revision was written against the
> issue's original framing — *"dispatch delegates to provider (ext#30)"* — and inventoried a
> 131-file cut under `src/atdd/mediate_worker_decisions/`. **That framing is cancelled and
> that scope now belongs to #1520.** This revision restates the manifest against the
> reframed issue.
>
> **Phase 2 has landed** — the 9 files at §1 are deleted. The §5 blocker was ruled on:
> #1480 sequences behind #1520 and does not widen. See §5.1 and §6.

## 0. The reframing

The operator has ruled: **the cmux runtime is not needed. Prune it outright. Do not delegate
it anywhere.** There is no core→provider seam and none is being built — nothing is relocated,
so the seam question that blocked the previous revision (#1483) is **moot**.

The governing test is not *"is this dead?"* but *"does this exist to manage a sub-worker?"*
If yes, it is pruned across the whole chain — wagon → feature → WMBT → acceptance → test →
code → convention → registry entry.

---

## 1. Scope

| target | files | LOC |
|---|---:|---:|
| `src/atdd/runtime/agent_control/` | 8 | 952 |
| `src/atdd/runtime/multiplexer.py` | 1 | 62 |
| **total** | **9** | **1014** |

**Survives:** `src/atdd/runtime/worktree.py` (263 LOC) is real lifecycle infrastructure and
stays. `runtime/elicit.py` and `runtime/interlocking/` are out of scope and untouched.

⚠️ `src/atdd/coach/utils/multiplexer.py` is a **different file** and belongs to #1519.

**Why this got simpler than the previous revision:** the earlier plan required retyping
`multiplexer.attach_view`, whose handle is typed against `agent_control.AgentHandle`. Since
the multiplexer is now also pruned, that rewire evaporates — the seam and both sides of it go
together. This is a straight deletion, not a retype-then-delete.

Method: unanchored grep for `runtime[./]agent_control` and `runtime[./]multiplexer` over
`src/**/*.py` and `tests/**/*.py`, then manual classification of each hit as an **executable
import** vs a **docstring/comment mention**. Anchored `^\s*(from|import)` patterns return
false zeroes and are not used. Counts are verified against this tree, not inherited.

---

## 2. Consumer classification

### 2.1 Executable importers — 8 sites in 6 files

| consumer | line | imports | in scope of #1480? |
|---|---|---|---|
| `src/atdd/mediate_worker_decisions/apply_decision/composition.py` | 67 | `agent_control::CmuxAgentController` | ⛔ **NO — see §5** |
| `src/atdd/mediate_worker_decisions/surface_worker_decisions/tests/test_y002_unit_002_spec_values_carry_policy_fields.py` | 19 | `agent_control::DispatchSpec` | ⛔ **NO — see §5** |
| `tests/architecture/test_layer_imports.py` | 136 | `multiplexer::Multiplexer` | ✅ yes |
| `tests/incident_defenses/test_incident_defenses_suite.py` | 274 | `agent_control::DispatchSpec` | ✅ yes |
| `tests/runtime/test_e039_unit_001_agent_control_typed_surface.py` | 28, 43, 53 | `agent_control::{AgentController, DispatchSpec, ReadyResult, AgentEvent, AgentSignal, AgentHandle}` | ✅ yes |
| `tests/runtime/test_e039_unit_001_agent_control_typed_surface.py` | 92 | `multiplexer::Multiplexer` | ✅ yes |

### 2.2 Mention-only — no code change required to delete

These name the modules in docstrings or comments and do **not** import them. They are listed
because a raw grep overstates the blast radius by ~3× if they are not filtered out.

`mediate_worker_decisions/apply_decision/src/application/ports.py:13`,
`…/apply_decision/src/integration/agent_control_applier.py:1,16`,
`…/surface_worker_decisions/src/domain/decision_surfacing_policy.py:9,11`,
`…/surface_worker_decisions/src/domain/surfacing_renderer.py:24`,
`…/surface_worker_decisions/src/presentation/surfacing_values_provider.py:5`,
`src/atdd/observer/__init__.py:7`, `tests/fixtures/__init__.py:10`, `tests/fixtures/agent.py:8`.

### 2.3 Architectural naming — must be updated in the deletion commit

Not importers, but they *name* the layers and would go stale:

- `src/atdd/runtime/__init__.py:5,8` — documents both as runtime layers
- `src/atdd/runtime/worktree.py:22-23` — layering docstring naming both
- `docs/coach-decomposition.md` — §3.3 layering table (lines 168, 179-181), §4.8/§4.9, 531,
  620, 642, 697, 852-854
- `README.md:416,638`

### 2.4 Boundary-policing tests — pruned, not repaired

`tests/architecture/test_layer_imports.py` (14, 43, 45, 47, 49, 51, 133-136),
`tests/incident_defenses/test_worktree_safety.py:214`,
`tests/incident_defenses/test_incident_defenses_suite.py:274`,
`tests/runtime/test_e039_unit_001_agent_control_typed_surface.py` (11, 28, 43, 53, 92, 119-124).

These police a boundary that will no longer exist. Each was read individually; where a file
asserts something broader than the agent_control/multiplexer boundary, only the
boundary-specific part is removed.

---

## 3. Plan chain

`plan/govern_lifecycle/{E014,E038,E039,E043}.yaml`, plus three feature files
(`cmux_native_worker_launcher.yaml`,
`extract_runtime_agent_control_and_close_spawn_cluster.yaml`, `orchestrate_pane_mode.yaml`).

⚠️ The feature files live in the **surviving** `govern_lifecycle` wagon — **edit, do not
delete**, unless the whole feature dies with the code.

**E039 does not split.** It carries a single acceptance `AC-UNIT-001` whose statement covers
both layers jointly — *"agent_control exposes the §4.8 typed surface **and** multiplexer
exposes the §4.9 view-only Protocol, and neither imports the sibling runtime layer."*
Pruning one layer alone leaves the acceptance half-true and
`test_e039_unit_001_agent_control_typed_surface.py` still asserting the surviving surface.
**A multiplexer-only partial is therefore not a clean landing.**

---

## 4. Train topology

| wagon | plan path | train |
|---|---|---|
| `wagon:govern-lifecycle` (this issue's plan chain) | `plan/govern_lifecycle/` | `train:self-compliance:validate-lifecycle` |
| `wagon:mediate-worker-decisions` (the blocking consumer) | `plan/mediate_worker_decisions/` | `train:issue-lifecycle:drive-state-machine` |

**These are different trains.** `validate-conventions` makes all wagons of a *shared* train
atomic; it does not make wagons of *different* trains atomic. So the widening question for
#1480 is materially different from the sibling slices — see §5.

---

## 5. Blocker — one live production consumer outside scope

`src/atdd/mediate_worker_decisions/apply_decision/composition.py:67`:

```python
def build_apply_use_case_from_repo(
    repo_root: Optional[Path] = None,
) -> ApplyDecisionUseCase:  # pragma: no cover - exercised by live smoke
    from atdd.runtime.agent_control import CmuxAgentController
```

This is **production source**, not a test. It is a lazy import inside a composition-root
factory marked `# pragma: no cover - exercised by live smoke`, so a static coverage read will
not surface it and the import error would fire at call time, not import time. A second real
importer sits in the same wagon's tests
(`surface_worker_decisions/tests/test_y002_unit_002_spec_values_carry_policy_fields.py:19`).

Both live in `wagon:mediate-worker-decisions`, which is owned by **open issue #1520 —
"Prune mediate_worker_decisions worker-orchestration runtime from core"** and sits on
`train:issue-lifecycle:drive-state-machine`.

The worker brief for #1480 asserted *"there is no surviving functional importer outside its
own tests."* **That assertion is false.**

**Two dispositions were available and the choice was the operator's** — see §5 of the issue
thread. Either #1520 lands first and #1480 follows unblocked, or #1480 widens to absorb the
two consumer sites, which would reach across a train boundary rather than within one.

### 5.1 Ruling — sequence behind #1520

**The operator ruled for the first disposition: #1480 sequences behind #1520 and does not
widen.** #1480 deletes nothing under `src/atdd/mediate_worker_decisions/`; the two consumer
sites at §2.1 are #1520's to remove, on its own train. This keeps the cut inside
`train:self-compliance:validate-lifecycle` rather than reaching across a train boundary.

The consequence is that **this branch does not stand alone on `main`.** Merged before #1520,
the two consumer sites would import `atdd.runtime.agent_control`, which no longer exists —
and the production one
(`apply_decision/composition.py:67`) is a lazy import inside a `# pragma: no cover` factory,
so it fails at *call* time, not import time. Merge order is a correctness constraint here,
not a preference.

---

## 6. Status

Phase 1 (inventory) complete against the reframed scope. **Phase 2 (deletion) landed** in
`refactor: prune the relocated cmux runtime from core` — the 9 files at §1, plus the plan
chain at §3, the boundary-policing tests at §2.4, and the architectural naming at §2.3.

### 6.1 Plan-chain note — two WMBTs are named E031

`wmbt:spawn-agents:E031` is removed (its sole surviving acceptance `AC-UNIT-003` bound
`runtime/agent_control/cmux_launch.py::build_agent_seed_argv`).
`wmbt:govern-lifecycle:E031` is the **emergency-bypass** WMBT, is unrelated, and is
**untouched**. The bare string `E031` is ambiguous in this repo; always qualify it by wagon.

### 6.2 Enforce ratchet

Re-recorded, tightened only — no count raised:

| rule | before | after |
|---|---:|---:|
| `coder.dead-code.reachability` | 59 | 58 |
| `coder.logging.coach-silent-swallow` | 248 | 240 |
| `coder.refactor.complexity-cognitive` | 131 | 129 |
| `coder.refactor.complexity-cyclomatic` | 149 | 147 |
| `coder.refactor.complexity-length` | 76 | 74 |
| `coder.refactor.complexity-nesting` | 173 | 171 |
| **total** | **1096** | **1079** |

### 6.3 Verification method — throwaway scratch branch

Because §5.1 leaves this branch unable to stand alone on `main` until #1520 lands, it cannot
be validated in place: the two surviving consumer sites would fail against the deleted
modules, and that red is an artefact of merge order rather than a defect in this cut.

Verification therefore runs on a **throwaway branch that simulates #1520 having landed**
(`scratch/verify-1480-with-1520-simulated`), which deletes the whole
`src/atdd/mediate_worker_decisions/` tree and its plan chain. That is a *superset* of the two
consumer sites at §2.1 — it models #1520 in full rather than the minimal cut, which is the
stricter and more honest simulation.

**That branch is never pushed and is discarded after the run.** It exists only to answer
"does this cut come out green once its blocker has landed?" Nothing red is pushed against
`main`.
