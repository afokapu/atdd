# SMOKE Test Audit

Classification of `# Phase: SMOKE` acceptance tests against real-infrastructure criteria.

| acceptance-URN | entry-point-coverage | assertion-target | handoff-coverage | incident-cross-ref |
|---|---|---|---|---|
| acc:observe-and-correct:E003-SMOKE-001 | atdd-shim CLI subprocess | output.log contains CORRECTION_RECEIVED | dispatcher.dispatch → cli-return.jsonl → shim → agent stdin | #862 (rewritten from PersonaShim direct) |
| acc:observe-and-correct:E003-SMOKE-002 | atdd-shim CLI subprocess (`python -m atdd.coach.shim`) | captured stdout contains STDOUT_SENTINEL_E003_SMOKE_002 | shim pty → sys.stdout.buffer → operator-visible terminal | #843 (stdout forwarding) |
| acc:observe-and-correct:E004-SMOKE-001 | atdd spawn / cmd_spawn | shim is surface foreground process (ppid check), output.log grows | cmd_spawn → PersonaShim (via atdd-shim) → agent pty | #841 (spawn dispatch wiring) |

## Histogram

Breakdown of SMOKE acceptance rows by structural-bypass cause.

| cause | count |
|---|---|
| entry-point-coverage (synthetic stub, not real CLI) | 1 (E003-SMOKE-001 — retrofitted in #862) |
| synthetic-fixture (FakeMultiplexer / _SYNTHETIC_AGENT) | 0 (suppressed or retrofitted) |
| producer-only assertion (no consumer-side check) | 0 |
| handoff-gap (producer→consumer not in one test) | 0 |

## Future Tracking

Post-SMOKE regression metric — tracks bugs discovered after SMOKE passed CI.

| release-wave | post-SMOKE-bugs | expectation |
|---|---|---|
| v3.83.x | 2 (startup race #862, no-submit #862) | 0 |
| v3.84.x | TBD | 0 |
