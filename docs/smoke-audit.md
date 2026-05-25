# SMOKE Acceptance Audit

**Created:** 2026-05-25
**Issue:** #855 — Investigate Smoke Test Systemic False Greens
**WMBT:** `wmbt:govern-lifecycle:E027`

Four production bugs shipped through green-SMOKE in the 2026-05-21 → 2026-05-24 session.
Each SMOKE test was technically passing — the assertion it made was true under the fixture
conditions it set up. Those conditions were not representative of production. This document
classifies every `phase: SMOKE` acceptance by structural cause and records the histogram
of bypass patterns.

---

## Classification Table

| acceptance-URN | entry-point-coverage | assertion-target | handoff-coverage | incident-cross-ref |
|---|---|---|---|---|
| acc:observe-and-correct:E003-SMOKE-001-correction-loop-end-to-end | synthetic (PersonaShim direct) | output.log content | producer-only (shim delivers; consumer assertion missing) | #824, #841, #854 |
| acc:observe-and-correct:E003-SMOKE-002-operator-stdout-visible | synthetic (atdd.coach.shim subprocess) | proc.stdout bytes | N/A (single component) | #843 |
| acc:observe-and-correct:E004-SMOKE-001-real-spawn-uses-shim-process-tree | real (atdd spawn via _ProcessLaunchingFakeMx) | process-tree parentage | partial (process spawned; cli-return consumer not verified) | #854 |
| acc:govern-lifecycle:P001-SMOKE-002-close-the-loop-feedback | real (atdd spawn via fake_shim) | pty_stdin_bytes + convergence | both ends (producer writes + consumer reacts) | #825 |
| acc:govern-lifecycle:E027-SMOKE-001-audit-covers-all-current-smoke-acceptances | real (atdd repo graph CLI) | JSON output completeness | N/A (meta-validator) | #855 |
| acc:govern-lifecycle:E028-SMOKE-001-validate-planner-clean-after-retrofit | real (atdd validate planner CLI) | exit code 0 | N/A (meta-validator) | #855 |
| acc:govern-lifecycle:E029-SMOKE-001-retrofitted-smokes-pass-in-ci-without-bypasses | real (CI run, no bypass flags) | test suite result | both ends (post-retrofit) | #855 |
| acc:govern-lifecycle:L002-SMOKE-001-meta-walker-zero-hits-on-post-retrofit-repo | real (walk_all_smoke_acceptances_for_anti_patterns) | anti-pattern hits list | N/A (meta-validator) | #855 |

---

## Histogram — Structural Bypass Cause

| structural-cause | count | description |
|---|---|---|
| synthetic-fixture / entry-point-bypass | 2 | Test drives a synthetic subprocess or direct class instantiation instead of the real CLI entry point |
| producer-only / handoff-gap | 2 | Test asserts on the producer side (artifact written) without verifying the consumer received it |
| real-entry-point / partial-handoff | 1 | Test drives real spawn but does not verify the full handoff path |
| real-entry-point / full-coverage | 3 | Test drives real entry point and verifies operator-observable behavior end-to-end |

**Total classified:** 8 SMOKE acceptances (as of 2026-05-25)

### Cause definitions

- **synthetic-fixture / entry-point-bypass**: SMOKE test instantiates a class directly (`PersonaShim(`)
  or calls a subprocess with a synthetic command (`cat`, `sleep`, embedded Python script) rather than
  routing through the real CLI entry point (`atdd spawn`, `atdd coach`). The production wiring —
  `_inject_agent_env`, `_build_shim_command`, adapter command construction — is bypassed entirely.
  Root cause of **#854** (Popen crash invisible to synthetic E003-SMOKE tests).

- **producer-only / handoff-gap**: SMOKE test asserts only on the producer side (e.g., artifact
  written to `output.log` or `cli-return.jsonl`). When the feature has a producer→consumer handoff,
  the consumer side is never exercised. Test passes green even when the consumer is completely
  unwired. Root cause of **#824** (cli-return consumer never wired, SMOKE green because it only
  checked that the producer wrote the file).

- **real-entry-point / partial-handoff**: SMOKE test uses the real CLI entry point but does not
  verify the full end-to-end handoff. The process tree is correct but the correction delivery
  to the agent's stdin is not asserted.

- **real-entry-point / full-coverage**: SMOKE test drives the real CLI entry point and asserts
  on operator-observable behavior at both ends of the handoff. This is the canonical shape.

---

## Lived Incident Cross-Reference

| incident | issue | SMOKE that should have caught it | structural cause | bypass mechanism |
|---|---|---|---|---|
| cli-return consumer not wired | #824 | acc:observe-and-correct:E003-SMOKE-001 | producer-only / handoff-gap | SMOKE asserted producer wrote cli-return.jsonl; no consumer existed |
| shim swallows pty output | #843 | acc:observe-and-correct:E003-SMOKE-002 | synthetic-fixture + producer-only | SMOKE asserted on output.log; never checked operator-visible stdout |
| RED tests in consumer wheel | #846 | (no relevant SMOKE; coverage gap) | missing SMOKE | No SMOKE for "consumer entry points don't surface RED tests" |
| Shim Popen crashes on real command | #854 | acc:observe-and-correct:E003-SMOKE-001/002 | synthetic-fixture / entry-point-bypass | E003-SMOKE used Python stub; _inject_agent_env + _build_shim_command never called |

---

## Future Tracking

Post-retrofit regression metric. Expectation: zero post-SMOKE production bugs per release wave
from v3.83.0 onwards. Any non-zero entry must reference the root-cause issue and the WMBT
whose SMOKE test failed to catch it.

| release-wave | post-SMOKE-bugs | expectation | notes |
|---|---|---|---|
| v3.83.x | 0 | 0 | Baseline established after E028/E029 retrofit (issue #855) |
| v3.84.x | — | 0 | (pending) |
| v3.85.x | — | 0 | (pending) |

**Maintenance rule:** When a production bug is discovered after a SMOKE phase passed green,
add a row here with `post-SMOKE-bugs > 0`, link the root-cause issue, and identify which
WMBT SMOKE acceptance failed to catch it. Then author a new WMBT (or extend existing) to
tighten the coverage.

---

## Remediation Plan

| phase | action | WMBT |
|---|---|---|
| E028 GREEN | Extend smoke.convention.yaml with 3 anti-pattern rules | wmbt:govern-lifecycle:E028 |
| E028 GREEN | Create planner-side validator test_smoke_synthetic_fixture_bypass.py | wmbt:govern-lifecycle:E028 |
| E029 GREEN | Retrofit test_e003_smoke_001 to use real atdd spawn path | wmbt:govern-lifecycle:E029 |
| E029 GREEN | Retrofit test_e003_smoke_002 to remove _SYNTHETIC_AGENT | wmbt:govern-lifecycle:E029 |
| E029 GREEN | Remove ATDD_RUN_SMOKE=1 opt-in gate from test_e004_smoke_001 | wmbt:govern-lifecycle:E029 |
| L002 GREEN | Implement walk_all_smoke_acceptances_for_anti_patterns meta-walker | wmbt:govern-lifecycle:L002 |
