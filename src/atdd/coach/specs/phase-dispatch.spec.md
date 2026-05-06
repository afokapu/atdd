# SPEC-COACH-PHASE-DISPATCH

> **Title**: Coach phase-driven dispatch for repo rules
> **Issue**: #416 (substrate Track-F, wave-s2)
> **Spec source**: `docs/specs/atdd-repo-substrate-spec-v12.md` §8.1 (Tier-1 dispatch per phase)
> **Companion**: coach v6 §6.5 (phase-validator selection)
> **Status**: ratified — implementation lives in
> `src/atdd/coach/utils/phase_dispatch.py`.

## 1. Background

Pre-substrate, `atdd validate <phase>` dispatched by toolkit *archetype*
(`planner | tester | coder | coach`). Coach v6 §6.5 introduces
*phase-driven* dispatch — the validator set executed at a coach session
depends on the lifecycle phase the agent is in (`RED | GREEN | SMOKE |
REFACTOR`) rather than which archetype owns the rule.

The substrate adds repo-derived rules to the registry: WMBT acceptances,
train acceptances, and security rules whose `bound_acceptance_urn`
resolves to one of the former. Each repo rule carries an
`identity.phase` value populated onto `RuleMetadata.phase` by the
walker. This spec pins how coach selects validators per phase against
that field.

This spec covers the substrate-side selection logic only — the runtime
emission of `Violation` records is the concern of the three substrate
runners (#411 harness, #412 metric, #422 security). Those runners emit
violations based on outcome regardless of coach phase; **coach is the
sole interpreter**.

## 2. Validator-set formula

For a coach session entering phase **X**, the active validator set is:

```
S(X) =
    { toolkit validators whose archetype gates X }                  # existing behavior
  ∪ { repo rules where RuleMetadata.phase == X }                    # §8.1 paragraph 3
  ∪ { repo rules where RuleMetadata.phase == "GREEN", if X == RED } # §8.1 paragraph 5 — RED expects red
  ∪ {                                                               # §8.1 paragraph 4 — REFACTOR sweep
        every rule (toolkit or repo) where
          RuleMetadata.disposition == "strict",
        if X == "REFACTOR"
    }
```

The substrate's selection helper —
`atdd.coach.utils.phase_dispatch.select_validator_set(phase, registry)` —
returns the union of the second, third, and fourth sets (the toolkit
`archetype` selection stays in `atdd validate`). Coach merges the two
when assembling the run list.

### 2.1 Source-kind irrelevance

The selection reads `RuleMetadata.phase` directly. It does **not** care
whether the rule originated from a WMBT acceptance, a train acceptance,
a security rule, or a `*.convention.yaml` toolkit rule. Phase is the
canonical dispatch field per §8.1.

### 2.2 Security-rule dispatch (§8.1 line 584)

Security rules registered via #422 carry a populated
`RuleMetadata.bound_acceptance_urn`. Their *own* `RuleMetadata.phase`
is informational; dispatch reads the **bound** rule's phase instead.

```
phase_for_dispatch(rule) =
    bind_rule(rule.bound_acceptance_urn).phase   if rule.bound_acceptance_urn is set
    rule.phase                                   otherwise
```

This branch is implemented unconditionally so #422 (security
registration) lands without a follow-up patch. Pre-#422 it is a no-op
because no security rules are in the registry — every rule has
`bound_acceptance_urn is None` so the second branch wins.

When a security rule's `bound_acceptance_urn` does not resolve in the
registry, the rule is dropped from selection — the substrate
enforcement rule
`security-rule-must-have-acceptance-ref-resolved` (§7.3) surfaces this
condition at PLANNED phase, not at runtime dispatch. The selector
treats unresolved `bound_acceptance_urn` as "skip silently."

## 3. RED-vs-GREEN expectation handling

A `phase: GREEN` acceptance declares the contract should pass at
GREEN. By ATDD convention, the same acceptance should *fail* at RED
(proving the contract exercises behavior not yet implemented). The
substrate runners emit `Violation` records based on outcome regardless
of phase; **coach is responsible for interpretation**:

| Coach phase | Rule's `phase` | Outcome | Coach interpretation |
|---|---|---|---|
| RED | RED | violation | Failure (regression on RED scaffolding) |
| RED | GREEN | violation | **Expected** — RED expects red |
| RED | GREEN | no violation | **Regression** — the GREEN contract is already passing at RED |
| GREEN | GREEN | violation | Failure |
| GREEN | GREEN | no violation | Pass |
| SMOKE | SMOKE | violation | Failure |
| REFACTOR | any strict | violation | Regression (sweep) |

The "expected vs regression" classification is coach v6 §4.1
behavior; the substrate selector simply *includes* GREEN-phase rules at
RED and lets coach interpret. The classification helper
`classify_violation(coach_phase, rule)` is also exported from
`phase_dispatch.py` for callers that need it explicitly.

## 4. REFACTOR sweep semantics

At REFACTOR, the selector additionally returns every rule (toolkit OR
repo) where `RuleMetadata.disposition == "strict"`, **regardless of
that rule's phase**. The intent is a regression check before COMPLETE:
no strict-disposition rule is allowed to fail in REFACTOR even if its
phase has already passed.

"Both registries" in §8.1 paragraph 4 refers conceptually to
toolkit-conventions and repo-rules. Both live in the same
`bind_rule()` cache (`_REGISTRY_CACHE` in
`src/atdd/coach/utils/rule_binding.py`); the selector iterates the
unified registry via `iter_rules()`.

### 4.1 Suppression markers — ineffective for repo rules

Per spec §8.5, the disposition gate appends repo-rule strict failures
unconditionally at REFACTOR. Suppression markers
(`# atdd:suppress(repo.<rule_id>) [UNTIL=<date>]`) do not silence
them. Toolkit-rule strict failures swept at REFACTOR retain the
existing `assert_disposition_satisfied` semantics (toolkit conventions
can use `# atdd:suppress(...)` for the migration debt cases that
disposition was designed for). The selector does not introduce a new
"REFACTOR suppression bypass"; it only includes the rules — gate
behavior is unchanged.

## 5. Example trace

Fixture WMBT
(`src/atdd/tester/validators/fixtures/phase_dispatch/mixed_phases.yaml`)
declares three acceptances:

| Acceptance | Phase | Rule-id |
|---|---|---|
| `acc:phase-dispatch:D001-UNIT-001-red-fixture` | RED | `repo.phase-dispatch.D001-acc-unit-001` |
| `acc:phase-dispatch:D001-UNIT-002-green-fixture` | GREEN | `repo.phase-dispatch.D001-acc-unit-002` |
| `acc:phase-dispatch:D001-UNIT-003-refactor-fixture` | REFACTOR | `repo.phase-dispatch.D001-acc-unit-003` |

Selector behavior:

| Coach phase | Selected repo rules |
|---|---|
| RED | { unit-001 (phase=RED), unit-002 (phase=GREEN — RED expects red) } |
| GREEN | { unit-002 (phase=GREEN) } |
| SMOKE | { } — no fixture rule pinned to SMOKE |
| REFACTOR | { unit-001, unit-002, unit-003 } — all strict |

The integration test
(`test_phase_dispatch.py::test_select_validator_set_against_mixed_phases_fixture`)
asserts this trace.

## 6. Public API

```python
from atdd.coach.utils.phase_dispatch import (
    select_validator_set,
    classify_violation,
    PhaseDispatchError,
)

# Returns Iterable[RuleMetadata].
selected = select_validator_set(coach_phase="RED")

# Returns "expected" | "regression" | "failure" | "pass".
classification = classify_violation(coach_phase="RED", rule=meta, violation_emitted=True)
```

`select_validator_set` accepts an optional `registry` argument (an
`Iterable[RuleMetadata]`) for tests; live callers pass nothing and the
function consumes `iter_rules()` from the unified cache. Phase strings
are case-insensitive; the function normalizes to upper-case internally
and rejects unknown phases with `PhaseDispatchError`.

## 7. Out of scope

* Spawn-harness `wmbt_rules` / `train_rules` / `security_rules` blocks
  (issue #417, §8.2).
* Risk-score archetype breakdown (issue #418, §8.3).
* Train scope detection at SMOKE (issue #441 prospective, §8.4).
