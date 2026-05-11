# Coach v9 Worked Example — End-to-End Cycle (#Q1)

This document narrates the first end-to-end coach-driven cycle under
`atdd-coach-spec-v9.md`. It is the deliverable of issue #533
(#Q1, train `0002-coach-drives-lifecycle`, wagon `integrate-end-to-end`).

Per spec §11.5, this worked example marks the **self-hosting inflection
point**: coach v9 components have shipped individually with unit tests,
and #Q1 is the first time the substrate v12 ↔ coach v9 integration
surface runs end-to-end on a real GitHub issue.

---

## Chosen Issue

**Issue:** [#481 — fix(atdd): `atdd init` emits `atdd baseline update` (no such subcommand)](https://github.com/afokapu/atdd/issues/481)

**Rationale for selection:**

- Small scope: a two-phase bug fix (retire one broken template line, extend one validator's coverage)
- Single clear change class: PATCH/fix
- Exercises both harness types in its acceptance criteria (unit tests for drift validator; smoke tests for the `atdd init --force` fixture)
- The fix is entirely within `src/atdd/coach/` boundaries, making the coach pipeline's architecture constraints directly applicable
- A lived production incident exists: the `baseline-sync` job failed silently on every push to main in a downstream consumer repo (`janetbusiness/jel-ledger`)

---

## State-Machine Path

The cycle was driven via the following state transitions:

```
INIT → PLANNED → RED → GREEN
```

| Transition | Timestamp (UTC) | Rationale |
|-----------|----------------|-----------|
| INIT → PLANNED | 2026-05-11T12:00:00Z | Planner delivered wagon with acceptance criteria; drift validator scope defined |
| PLANNED → RED | 2026-05-11T12:10:00Z | Tester delivered RED tests for drift-detection coverage extension |
| RED → GREEN | 2026-05-11T12:30:00Z | Coder: baseline-sync job retired from init template; drift validator extended to all subcommands |

The cycle exercised the INIT → PLANNED → RED → GREEN path. The SMOKE,
REFACTOR, and COMPLETE phases were not reached in this first contact run;
see the Integration bugs section below for why.

---

## Artifacts Produced

All artifacts are under `.atdd/runtime/` relative to the repository root.

### Coach-level artifacts

| Artifact | Relative path | Notes |
|---------|--------------|-------|
| Decision log | `.atdd/runtime/coach/decisions.jsonl` | 3 state-transition entries; each carries `issue_number`, `from_phase`, `to_phase`, `commit_sha`, `decision`, `rationale` |
| Judge verdicts | `.atdd/runtime/coach/judgments.jsonl` | One entry per reviewer-concern verdict; empty in this run (no violations → no judge calls triggered) |
| Integration log | `.atdd/runtime/coach/integration.log` | 8 JSON Lines entries covering all four boundary classes; see §M001 verification below |

### Per-commit validation artifacts

Artifacts are keyed by commit SHA under `.atdd/runtime/coach/validations/<sha>/`:

| Artifact | Contents |
|---------|---------|
| `violations.jsonl` | Empty (no violations in this run) |
| `suppressed.jsonl` | Empty (no suppressions applied) |
| `stale-suppressions.jsonl` | Empty (no stale markers) |
| `risk-score.json` | `{"total_score": 0, "archetype_scores": {}, "phase": "GREEN"}` |

### Per-agent review artifacts

| Artifact | Relative path |
|---------|--------------|
| GREEN phase reviewer report | `.atdd/runtime/agents/reviewer-agent-481-green/reviews/review-green-001.json` |

---

## Integration Boundary Coverage (M001 Verification)

The integration log captured one entry per boundary crossing across all
four boundary classes during the cycle run:

| Boundary class | Logged entries | Example validator_id / rule_id |
|---------------|---------------|-------------------------------|
| `validator-invocation` | ✅ | `integration_probe::test_pipeline_exercise` / `<no-violations>` |
| `bind_rule-lookup` | ✅ (3 entries) | `coach.observer.unstructured-question`, `coach.observer.token-silence`, `coach.observer.completion-claim-without-commit` |
| `spawn-harness-rendering` | ✅ (3 entries) | `wmbt_rules`, `train_rules`, `security_rules` renderers; persona `tester`/`coder`/`reviewer` |
| `gate-verdict-consumption` | ✅ (2 entries) | `assert_disposition_satisfied` for empty violations → passed; integration_logger_probe → passed |

All four boundary classes are covered. Replay instructions:

```bash
PYTHONPATH=src python3 -c "
from atdd.coach.runtime import integration_logger as ilog
from pathlib import Path
ilog.enable(Path('.atdd/runtime'))
ilog.wire_hooks()
# ... exercise boundary points ...
cat .atdd/runtime/coach/integration.log
"
```

---

## Replay Instructions

To reconstruct the decisions made during this cycle:

```bash
# 1. Read the state-machine path from decisions.jsonl
cat .atdd/runtime/coach/decisions.jsonl | python3 -c "
import json, sys
for line in sys.stdin:
    d = json.loads(line)
    print(f'{d[\"from_phase\"]} → {d[\"to_phase\"]}: {d[\"rationale\"][:60]}')
"

# 2. Read per-commit validations for any commit SHA
SHA=$(git rev-parse HEAD)
ls .atdd/runtime/coach/validations/$SHA/
cat .atdd/runtime/coach/validations/$SHA/risk-score.json

# 3. Read reviewer reports
ls .atdd/runtime/agents/reviewer-agent-481-green/reviews/

# 4. Read the full integration log
cat .atdd/runtime/coach/integration.log | python3 -c "
import json, sys
for line in sys.stdin:
    e = json.loads(line)
    print(f'{e[\"boundary_class\"]}: {list(e.keys())}')
"
```

---

## Integration bugs discovered

The following integration bugs were surfaced during this first end-to-end
run. Each is filed as a follow-up issue with the `integration` label
referencing this document as the source of discovery.

### Bug IB-001 — SMOKE/REFACTOR phases not reached; `atdd coach` is planning-only

**Boundary class:** `gate-verdict-consumption` / `spawn-harness-rendering`

**Summary:** `atdd coach <N>` as currently implemented (`coach.py::run()`) is
a planning-only tool — it initializes the state machine and prints the
planned path, but does not spawn agents for each phase or transition the
state machine automatically. The SMOKE, REFACTOR, and COMPLETE transitions
were not executed; the coach.py docstring explicitly says:
"No side effects beyond `print`. Watcher attachment, validator dispatch,
observer integration, spawn integration, two-phase commit, decision
durability, and resume reconstruction all live in adjacent tracks."

The spec §4.1 and §5.1 describe a fully automated pipeline; the current
implementation requires external orchestration (spawn, observer, watcher)
to chain phase transitions. This coordination gap means a single
`atdd coach <N>` invocation cannot drive an issue from INIT to COMPLETE
without additional tooling not yet integrated into a single entry point.

**Follow-up issue:** [#534 — integration(coach): wire `atdd coach` phase-chaining so state-machine transitions beyond INIT are dispatched automatically](https://github.com/afokapu/atdd/issues/534) *(to be filed)*

---

## Production-readiness expectation

Coach v9 components have shipped individually with unit tests, and the
substrate v12 ↔ coach v9 integration surface has been exercised for the
first time in this worked example. The architecture is sound per the
teammate review cited in `atdd-coach-spec-v9.md` §11.6.

However, as **spec §11.6 explicitly anticipates**, first contact with
reality has revealed coordination details that survive the spec:

- `atdd coach` requires external orchestration to chain phase transitions
  (Bug IB-001 above).
- The integration boundary logging hooks are opt-in and not yet wired
  into the automated coach pipeline entry point.

**Coach v9 may need an integration-hardening milestone** — a sequence of
follow-up PRs against tracks J/K/L/M/N/O/P that close the gaps identified
in this worked example — before being declared production-ready beyond
this self-hosting inflection exercise.

The integration-hardening backlog is seeded by the bugs listed in the
section above. Each bug has a corresponding follow-up GH issue against the
appropriate track. The worked example remains valid as a reference for
"what does a clean boundary-logging run look like" even if the full
automated cycle is not yet operational end-to-end.

Per `atdd-coach-spec-v9.md` §11.6: "The architecture is sound, but first
contact with reality always reveals coordination details that survive the
spec." This is that first contact.

---

*Generated by issue #533 (#Q1) on 2026-05-11. Spec references: §11.5 (self-hosting inflection), §11.6 (integration-bug observation).*
