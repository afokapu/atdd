# Removal manifest — #1480 (executes atdd-extensions #30)

> **Phase 1 deliverable. Nothing has been deleted.** This manifest classifies the 131
> files, names every core consumer, and specifies the required re-point.
>
> **Verdict: the removal cannot proceed as briefed.** The re-point the brief asks for
> ("core dispatch delegates to the provider") is the exact thing the provider's own
> architecture decision-of-record *rejects*, and the seam it prescribes instead **does not
> exist in core**. Two blockers and one scoping error are documented below; all three need
> a coach decision before Phase 2. See §5.

Method: AST import graph over all of `src/atdd` (`ast.ImportFrom`/`ast.Import`, `atdd.*`
only), plus a separate grep for **string-literal** module references — an AST scan
structurally cannot see `python -m "atdd...."`, and there is exactly one such consumer
(§2.3). Counts below are grep/AST-verified, not inherited.

---

## 1. The 131 files

Exactly 131 `.py` files, all under `src/atdd/mediate_worker_decisions/`:

| subtree | files | non-test | test |
|---|---|---|---|
| `bridge_cmux_feed/` | 61 | 21 | 40 |
| `feed_daemon/` | 39 | 16 | 23 |
| `surface_worker_decisions/` | 31 | 14 | 17 |
| **total** | **131** | **51** | **80** |

---

## 2. Classification

### 2.1 DELETE-safe — 0 files

**No file in the 131 is delete-safe today.** The three subtrees are a single connected
import component, and each has at least one live consumer *outside* the delete set. There is
no subset of the 131 that can be removed while leaving core and its siblings importable.

### 2.2 STILL-IMPORTED — the 131 is not a closed cut

The brief's premise is that `spawn.py` is the only core consumer. It is not, in two ways.

**(a) The real core consumers — 3 sites in 3 files (not one).** Note there are *two*
`spawn.py` files, and the one the brief names imports only `surface_worker_decisions`:

| consumer | line | imports | into |
|---|---|---|---|
| `src/atdd/coach/commands/spawn.py` | 660 | `surface_worker_decisions…presentation.surfacing_values_provider::provide` | **the 131** |
| `src/atdd/coach/commands/spawn.py` | 746 | `surface_worker_decisions…application.resolve_surfacing_values::resolve` | **the 131** |
| `src/atdd/coach/commands/coach.py` | 1388 | `coach_runtime…presentation.coach_runtime_cli::run` | `coach_runtime` |
| `src/atdd/coach/handlers/spawn.py` | 381 | `coach_runtime…presentation.attach_worker_daemon` | `coach_runtime` |

**(b) Two sibling wagons that are NOT in the delete set depend on the 131.** This is the
load-bearing finding: deleting the 131 breaks 59 further files that nobody scoped.

| dependent wagon | files | depends on | reachable from core? |
|---|---|---|---|
| `coach_runtime/` | 39 | `bridge_cmux_feed` (`live_smoke`, `src.domain.feed_item`, `src.integration.feed_event_source`), `feed_daemon` (`src.integration.signal_stop`, **and `feed_daemon_cli` via a `python -m` string** — §2.3) | **YES** — `coach.py:1388`, `handlers/spawn.py:381` |
| `coach_answer_escalation/` | 20 | `bridge_cmux_feed` (8 modules incl. `src.application.ports`, `src.domain.feed_reply_mapper`, `tests/_helpers`), `feed_daemon` (`live_smoke`) | **NO** — no importer outside itself (already orphaned; see §5.3) |

**True blast radius: 131 + 59 = 190 files across 5 of the 10 `mediate_worker_decisions/`
subtrees** — not 131 across 3.

### 2.3 The one non-import consumer

`coach_runtime/src/integration/daemon_manager.py:29` holds the feed_daemon CLI as a **string**:

```python
"atdd.mediate_worker_decisions.feed_daemon.src.presentation.feed_daemon_cli"
```

launched via `python -m`. An import-graph scan does not see this. Deleting `feed_daemon`
turns it into a runtime `ModuleNotFoundError` in a detached subprocess — a failure that no
import check and no unit test will catch at delete time.

### 2.4 SHARED — must stay

Untouched, and confirmed free of any import into the 131 (only prose mentions in two
docstrings): `apply_decision/` (23), `mediate_decision/` (26), `sense_decision/` (17),
`persistent_orchestrator/` (12), `commons/` (3).

**Dangling pointers to fix on delete:** `src/atdd/coach/conventions/coach.convention.yaml`
lines 64–66 name `mediate_worker_decisions/`, `feed_daemon/`, `bridge_cmux_feed/` as paths.

---

## 3. Scoping error: `surface_worker_decisions` is core policy, not relocated runtime

The 131 was cut by directory, not by ownership. `surface_worker_decisions` — the **only**
part of the 131 that `commands/spawn.py` actually uses — computes the launch **freedom set**
(`permission_mode` + `allowedTools`), sourced from `session.convention.yaml`. That is the
image of core's own obligations, and the boundary spec is explicit that they stay in core:

> **Does not own:** the *requirement* that decisions are mediated and corrections are
> structured — those stay core (`coach.execution.decisions-mediated-not-auto-executed`,
> `coach.execution.freedom-with-a-leash`, …). This workspace only carries them on a
> concrete transport.
> — `docs/atdd-workspace-cmux-claude-boundary.md` §4

The provider agrees mechanically: `atdd.workspace.yaml` declares
`command_injectable: true` — "the launch argv is **supplied**, not hardcoded". Someone must
supply it. That someone is core, and `surface_worker_decisions` is how.

So it splits, and should not be deleted wholesale:

| file | verdict |
|---|---|
| `src/domain/decision_surfacing_policy.py` | **KEEP** — core policy (freedom-with-a-leash) |
| `src/domain/surfacing_renderer.py` | **KEEP** — renders the policy to argv values |
| `src/application/resolve_surfacing_values.py` | **KEEP** — consumed by `spawn.py:746` |
| `src/application/ports.py` | **KEEP** — the probe port (transport-neutral) |
| `src/presentation/surfacing_values_provider.py` | **KEEP** — consumed by `spawn.py:660` |
| `src/integration/cmux_hook_probe.py` | **PROVIDER** — superseded by `adapter/readiness.py` |
| `src/presentation/dispatch_feed_hook_gate.py` | **PROVIDER** — the provider calls this "the (dead) `assert_dispatch_feed_hook_active` gate" |
| `live_smoke.py` + `tests/` (17) | follow their subject |

The genuinely relocated transport is **`bridge_cmux_feed` (61) + `feed_daemon` (39) = 100
files**, plus 2 cmux-coupled files from `surface_worker_decisions`. Not 131.

---

## 4. The required re-point — and why it cannot be written as briefed

The brief asks: *"how should dispatch delegate to the provider?"* The answer, from the
provider's own decision-of-record, is: **it must not.**

`atdd.workspace.cmux-claude/docs/agnostic-runtime-architecture.md` — status *"architecture
decision of record"*, explicitly superseding core tracker **#1327**:

> **Core never imports, spawns, or otherwise invokes the provider.** The provider never
> imports `atdd.*`. They meet only at an agnostic seam expressed as data/contract.

and §4, titled *"Why 'move-and-invoke' / 'core-daemon-runner' is REJECTED"*:

> A core daemon-runner that knows how to find, import, and drive the cmux provider's
> `FeedDaemon`/feed/session bakes cmux-shaped runtime assumptions into core… **Both are
> rejected.**

The prescribed model instead: **core dispatch reaches an agnostic hook; the extension
observes it and self-triggers its own spawn.** Core learns *that* the obligation is
satisfied, never *how*.

### 4.1 Blocker 1 — the prescribed seam does not exist in core

The DOR names this itself, as a core gap (§3, finding 3):

> Core's substrate binder is test-runner-only. `binder.provider_spawn` is hardwired to the
> `execution.*` contract… and invoked **only from tests** — **there is no agnostic
> production-invocation seam. That is a core gap**, to be filled by an agnostic hook
> (obligation + satisfier).

I verified this against the tree:

- Core's obligation node `coach.execution.dispatch-verifies-channel-live` exists — but its
  `implementation.type` is **`validator`** (an *admission-time* check that a transport
  provider declares `realizes`). It is not a runtime hook. Nothing calls a provider through it.
- The only provider registry in core is `atdd.state.providers` /
  `atdd.state.provider_seam` — a **state-sync** seam (`mirror()` / `detect_drift()`), a
  different capability entirely. There is no workspace/transport provider registry.

**So #1480 has an unstated prerequisite: the agnostic hook must be built first.** It is not a
line of re-pointing; it is a new core seam. Nothing in the issue scopes it.

### 4.2 Blocker 2 — the provider is not installed, and is not importable as a package

Even if a "just call the provider" re-point were sanctioned, it could not run:

- **Not installed here.** `.atdd/workspaces/` contains only `atdd.workspace.python-pytest`;
  `.atdd/substrate.lock.yaml` does not list `atdd.workspace.cmux-claude`. Core cannot resolve it.
- **Not importable.** The provider's adapters are **flat top-level modules**
  (`import cmux_rpc`, `from decision_channel import DecisionChannelAdapter`) — not a package.
  They require the adapter directory on `sys.path`. This is deliberate: `conformance/
  test_import_discipline.py` AST-scans to prove the provider never does `import atdd.*`.

### 4.3 The contradiction the coach must resolve

The provider package contradicts **itself**, and the two halves imply opposite Phase 2 plans:

| source | claim |
|---|---|
| `docs/agnostic-runtime-architecture.md` (DOR) | "Core never imports, spawns, or otherwise invokes the provider." Move-and-invoke **REJECTED**. |
| `adapter/launch.py` (docstring, line 6) | "This module is that composition — **the single entry the core dispatch calls** to launch a mediated worker." |

`adapter/launch.py` describes precisely the move-and-invoke design the DOR rejects. One of
the two is stale. **Which one is authoritative decides Phase 2**, and I will not guess:

- If the **DOR** holds → #1480 is blocked on building the agnostic hook (a new core seam,
  its own issue), and the deletion happens *after* the extension self-triggers.
- If **`adapter/launch.py`** holds → the DOR is stale, and #1480 needs the provider installed
  + a resolution/invocation path in core (which the DOR calls the "Phoenix" anti-pattern).

---

## 5. What I need from the coach

1. **Which seam is authoritative** — the DOR's agnostic hook (§4.3), or `adapter/launch.py`'s
   "core dispatch calls the provider"? This is the crux and everything else waits on it.
2. **Is the agnostic hook in scope for #1480, or a prerequisite issue?** It does not exist,
   and #1480 cannot land without it under the DOR model. My recommendation: **split it out** —
   #1480 becomes the deletion that *follows* the hook, and stays blocked until then.
3. **Confirm the `surface_worker_decisions` re-scope (§3)** — I read it as core policy that
   was mis-swept into the 131. If so, the delete set is 100 + 2, not 131, and
   `commands/spawn.py` needs **no re-point at all** (its imports stay valid).
4. **What happens to `coach_runtime` (39) and `coach_answer_escalation` (20)?** They are not
   in the issue but they die with the 131. `coach_answer_escalation` is already unreachable
   from core — it looks like a cadaver and may be a straight delete; `coach_runtime` is live
   (`coach.py:1388`, `handlers/spawn.py:381`) and is exactly the "spawn trigger" the DOR says
   the *extension* should own.

**Recommendation:** do not delete anything under the current issue scope. #1480 as written
would break core dispatch, 59 unscoped files, and one `python -m` subprocess that no test
covers. The removal is the *last* step of the agnostic-hook cutover, not the first.

---

## Appendix — the 12 import edges crossing out of the 131

```
CORE
  coach/commands/spawn.py -> surface_worker_decisions.src.application.resolve_surfacing_values
  coach/commands/spawn.py -> surface_worker_decisions.src.presentation.surfacing_values_provider

coach_runtime/  (39 files — NOT in the delete set)
  live_smoke.py            -> bridge_cmux_feed.live_smoke
                           -> bridge_cmux_feed.src.domain.feed_item
                           -> bridge_cmux_feed.src.integration.feed_event_source
                           -> feed_daemon.src.integration.signal_stop
  presentation/coach_runtime_cli.py -> feed_daemon.src.integration.signal_stop
  integration/daemon_manager.py:29  -> feed_daemon…feed_daemon_cli   [STRING, python -m]

coach_answer_escalation/  (20 files — NOT in the delete set)
  live_smoke.py                 -> bridge_cmux_feed.{live_smoke, src.domain.feed_item,
                                    src.integration.feed_event_source, src.integration.feed_reply_applier,
                                    src.integration.llm_coach}, feed_daemon.live_smoke
  src/application/answer_escalation.py  -> bridge_cmux_feed.src.application.ports
                                        -> bridge_cmux_feed.src.domain.feed_item
                                        -> bridge_cmux_feed.src.domain.feed_reply_mapper
  src/application/surface_escalations.py -> bridge_cmux_feed.src.application.ports
  src/domain/escalation_surfacing.py     -> bridge_cmux_feed.src.domain.feed_item
  tests/ (5 files)                       -> bridge_cmux_feed.src.domain.feed_item
                                         -> bridge_cmux_feed.tests._helpers
                                         -> bridge_cmux_feed.src.integration.feed_reply_applier
```
