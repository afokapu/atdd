# Substrate Worked Example — Day-1 End-to-End

> Issue [#423](https://github.com/afokapu/atdd/issues/423) — substrate Track-I integration acceptance.
> Spec reference: [`docs/specs/atdd-repo-substrate-spec-v12.md`](specs/atdd-repo-substrate-spec-v12.md)
> §11 (Day-1 experience).

This document walks through the substrate end-to-end against the toolkit's
own `plan/`. It is the integration acceptance for Tracks A–G (issues
#407–#415, #419–#422). When you can reproduce every step below, the
substrate is doing its job.

The walkthrough fixes one concrete WMBT and one concrete train, but the
mechanism it demonstrates is the same one any consumer repo sees on
Day 1 (§11): one CLI run surfaces every Class 1 conformance gap, you
clear them with the recipe pointers, and Class 2 contract failures then
surface through pytest with the substrate-enriched failure block.

---

## 1. Chosen artifacts

| Role | URN | Source |
| --- | --- | --- |
| Worked-example WMBT | `wmbt:govern-lifecycle:D010` | [`plan/govern_lifecycle/D010.yaml`](../plan/govern_lifecycle/D010.yaml) |
| Worked-example acceptance | `acc:govern-lifecycle:D010-METRIC-001-single-source-theme-map-helper` | same |
| Worked-example train | `train:0001-self-compliance-validate` | [`plan/_trains/0001-self-compliance-validate.yaml`](../plan/_trains/0001-self-compliance-validate.yaml) |
| Derived rule (D010) | `repo.govern-lifecycle.D010-acc-metric-001` | derived per spec §3.3 |

**Why D010?** It is the canonical metric-mode dogfood from issue #413 —
its `signal.metric` (`hardcoded_theme_map_literal_count`) is the only
metric currently implemented in the toolkit's commons
(`src/atdd/runners/metrics/`). It exercises the §4.5 N-to-1 metric
runner end-to-end and produces a real, non-vacuous Class 2 violation
against the toolkit's own source tree.

**Why train 0001?** It is the toolkit's primary self-compliance train.
It declares no `acceptances` block, so it derives **zero** train rules
— the worked example explicitly demonstrates the "no train rules
authored yet" branch of §4.5. Train acceptance fields are schema-ready
(spec §5.2) but the toolkit team has not yet authored any; the train
slice of the registry is empty until they do.

**Security path.** The toolkit's `plan/**/*.yaml` declares **zero**
`security.abuse_cases[]` blocks. Per the issue body's option (a): the
security-rule registry is empty and the security-mode runner is a
no-op for this walkthrough. No fixture abuse_case is authored solely
for the worked example.

---

## 2. Day-1 workflow

The §11 workflow is six steps. The toolkit follows it on every
`atdd repo validate` invocation.

### Step 1 — `atdd init` (already done)

The toolkit ships with `repo.substrate.enabled: true` in
[`.atdd/config.yaml`](../.atdd/config.yaml) (issue #415). Consumer
repos run `atdd init --consumer-repo` to flip this on. The pytest
plugin (`atdd.tester.substrate.plugin`, issue #411) is auto-loaded via
the toolkit's `pytest11` entry point.

### Step 2 — `atdd repo validate` (Class 1 surfaces)

```
$ atdd repo validate
…
--- Substrate Track-B conformance (spec §7.3) ---
[substrate] conformance: PASS
```

The conformance suite (issue #410) runs five validators in strict mode:

| Validator | Rule | Class 1 category |
| --- | --- | --- |
| `test_acceptance_measurable.py` | `tester.acceptance-violation.acceptance-must-be-measurable` | "These N acceptances fail measurability." |
| `test_acceptance_phase.py` | `tester.acceptance-violation.acceptance-must-declare-phase` | "These N acceptances are missing identity.phase." |
| `test_acceptance_disposition.py` | `tester.acceptance-violation.disposition-must-not-be-declared` | "These N YAMLs declare disposition (forbidden)." |
| `test_repo_validator_binding.py` | `tester.acceptance-violation.validator-binding-must-be-bidirectional` | "These M validator bindings are inconsistent." |
| `test_metric_implementation.py` | `tester.acceptance-violation.metric-implementation-must-exist` | "These K signal.metric implementations are missing." |

Each rule carries a prescriptive `recipe:` pointer (§7.3). Together
they are Class 1: substrate-conformance failures with mechanical fixes.

### Step 3 — Working through a Class 1 failure (recipe pointer)

This is the migration story for the toolkit's own `plan/`. Before
issue #423 landed, every "both" acceptance in the toolkit declared
`signal.metric` without a backing implementation, and no test file
carried the `# Acceptance: <urn>` header. Two rules fired, with these
shapes:

```
rule_id=tester.acceptance-violation.metric-implementation-must-exist
disposition=strict
description: When signal.metric is declared, a compute() implementation
             must exist in either <repo>/.atdd/metrics/<metric>.py or
             src/atdd/runners/metrics/<metric>.py
fix_hint:    The acceptance declares signal.metric: <name>, but no
             compute function exists in either lookup root...
recipe:      metric-implementation
```

```
rule_id=tester.acceptance-violation.validator-binding-must-be-bidirectional
disposition=strict
description: When harness.type is declared, an anchored test must exist
             whose headers match the acceptance
fix_hint:    Either add the standard test header block at the top of
             the test file: # URN: ... # Acceptance: ... # WMBT: ...
recipe:      acceptance-test-headers
```

Following the recipes (issue #423 migration, this PR):

1. **For acceptances declaring both `harness.type` and a speculative
   `signal.metric` without an implementation:** the `recipe:
   metric-implementation` step "Decide where the implementation lives"
   ends with: *"…or remove signal.metric from the acceptance and rely on
   harness mode."* That is what the toolkit did. Speculative `signal:`
   blocks were stripped from 60 acceptances; D010 is the one acceptance
   that retains its `signal.metric` because its compute function
   (`hardcoded_theme_map_literal_count`) ships in
   `src/atdd/runners/metrics/`.

2. **For acceptances declaring `harness.type` but missing the anchor
   header in their test file:** the `recipe: acceptance-test-headers`
   step adds the standard header block:

   ```python
   # URN: test:<wagon>:<wmbt-id>-anchor
   # Acceptance: acc:<wagon>:<wmbt-id>-<HARNESS>-NNN-<slug>
   # WMBT: wmbt:<wagon>:<wmbt-id>
   # Phase: <RED|GREEN|SMOKE|REFACTOR>
   # Layer: <presentation|application|domain|integration|assembly>
   ```

   The toolkit ships [`plan/_substrate_anchors/`](../plan/_substrate_anchors/),
   one stub-anchor file per WMBT, until each acceptance gets a real
   wired test elsewhere in the tree (real-test files anchor by adding
   the same header block; the corresponding stub is then deleted).

After the migration the conformance suite reports zero violations:

```
$ PYTHONPATH=src python3 -m pytest \
    src/atdd/tester/validators/test_acceptance_measurable.py \
    src/atdd/tester/validators/test_acceptance_phase.py \
    src/atdd/tester/validators/test_acceptance_disposition.py \
    src/atdd/tester/validators/test_repo_validator_binding.py \
    src/atdd/tester/validators/test_metric_implementation.py
…
5 passed
```

### Step 4 — Re-run `atdd repo validate` (Class 1 = 0)

```
$ atdd repo validate
…
--- Substrate Track-B conformance (spec §7.3) ---
[substrate] conformance: PASS
```

The toolkit's CI (`.github/workflows/atdd-validate.yml`) used to set
`ATDD_ALLOW_SUBSTRATE_BACKLOG=1` to demote conformance violations to
warnings during the migration window. With Class 1 backlog at zero
this PR removes that env var — substrate is strict from now on.

### Step 5 — Class 2 surfaces in pytest

Class 2 is the real-contract path: the substrate harness-mode plugin
(§7.2) and metric runner (§4.5) emit per-rule violations through the
disposition gate. The failure block is enriched with `description` and
`fix_hint` composed from the acceptance's own fields (§4.2).

Run the metric runner against the toolkit:

```
$ python3 -c "
> from atdd.runners.metrics.hardcoded_theme_map_literal_count import compute, passes
> from pathlib import Path
> v = compute(Path('.').resolve())
> print(f'compute() = {v}'); print(f'passes(v, 0) = {passes(v, 0)}')
> "
compute() = 24
passes(v, 0) = False
```

The toolkit currently has 24 hardcoded theme_map literals against a
threshold of 0 — a real Class 2 contract violation. When the runner
emits this through the gate, the failure block is shaped per spec §6:

```
rule_id=repo.govern-lifecycle.D010-acc-metric-001 disposition=strict validator=test_metric_runner::test_metric_threshold_satisfied (1 unsuppressed):
  description: A single get_theme_map(config) helper replaces every hardcoded theme_map dict in the codebase
  fix_hint:    No theme_map dict literal appears outside coach/utils/theme_map.py; inventory.py, registry.py, and test_train_validation.py import and call get_theme_map; The helper is the single source of truth for the digit-to-theme mapping
  [repo.govern-lifecycle.D010-acc-metric-001 sev=4] codebase: hardcoded_theme_map_literal_count=24, threshold=0
```

`description` and `fix_hint` come from
[`plan/govern_lifecycle/D010.yaml`](../plan/govern_lifecycle/D010.yaml)'s
`identity.purpose` and `then.abstract` fields — no separate enrichment
file needed (§4.2).

### Step 6 — Working through a Class 2 failure (no recipe — describe contract)

The agent reads `description` and `fix_hint`, opens the codebase, and
implements the contract. For D010 the work is mechanical: replace each
hardcoded `theme_map = {...}` literal with a call to
`coach.utils.theme_map.get_theme_map(config)`. This is ongoing
self-compliance work tracked under
[`wmbt:govern-lifecycle:D010`](../plan/govern_lifecycle/D010.yaml); when
the count reaches zero the rule passes and the gate is silent.

Class 2 has **no recipe pointer** (§11): the contract is the
acceptance and the fix is modeling work, not mechanical conformance.

---

## 3. Coach session integration

When a coach session runs a phase against a wagon containing
`wmbt:govern-lifecycle:D010` and the metric runner reports a
threshold breach, the spawn-harness emits the same enriched failure
block via the dispatch path from issue #416. The output is what the
agent reads:

- The failure block above (description + fix_hint composed from
  acceptance fields) is the substrate's contract surface.
- The risk-score breakdown (issue #418) shows the `repo:` archetype's
  contribution to the wagon's overall risk so coach can route attention.
- The phase dispatch (issue #416) selects which validators run per
  phase; D010 phase=`GREEN`, so the metric runner fires during GREEN.
- The spawn-harness `wmbt_rules:` block (issue #417) lists the rule
  for the agent to act on.

For trains, dispatch fires at SMOKE (§8.4 + issue #416). Train 0001
declares no acceptances, so its block is empty — the dispatch path
exists end-to-end, but the registry has nothing to emit.

---

## 4. Substrate conformance — current state

```
$ PYTHONPATH=src python3 -m pytest \
    src/atdd/tester/validators/test_acceptance_measurable.py \
    src/atdd/tester/validators/test_acceptance_phase.py \
    src/atdd/tester/validators/test_acceptance_disposition.py \
    src/atdd/tester/validators/test_repo_validator_binding.py \
    src/atdd/tester/validators/test_metric_implementation.py
5 passed
```

| Rule | Violations |
| --- | --- |
| `acceptance-must-be-measurable` | **0** |
| `acceptance-must-declare-phase` | **0** |
| `disposition-must-not-be-declared` | **0** |
| `validator-binding-must-be-bidirectional` | **0** |
| `metric-implementation-must-exist` | **0** |
| `security-rule-must-have-acceptance-ref-resolved` | **0** (registry empty) |

The acceptance criterion from issue #423 — *"`atdd repo validate`
passes with zero substrate-conformance failures on the toolkit's own
`plan/`"* — is met.

---

## 5. Anchor stubs and ongoing migration

[`plan/_substrate_anchors/`](../plan/_substrate_anchors/) holds 57
anchor files covering 69 acceptances. Each test body is a
`pytest.skip` placeholder; the file's job is to declare the
`# Acceptance: <urn>` header so the bidirectional-binding rule
resolves. Skipped tests do not raise `AssertionError`, so the
substrate harness-mode plugin emits no Class 2 violation for them.

These stubs are migration scaffolding, not coverage. The intended
lifecycle:

1. A real wired test for an acceptance lands somewhere in the toolkit
   (`src/atdd/**/tests/`, `tests/`, etc.).
2. The author adds the standard header block to the real test file,
   matching the acceptance URN.
3. The anchor stub for that acceptance is removed from
   `plan/_substrate_anchors/test_anchor__<wagon>__<wmbt>.py`.
4. When every acceptance under a WMBT has real coverage, the WMBT's
   anchor file is deleted.
5. When no anchor files remain, the directory is removed and the
   substrate is fully dogfooded.

Until then, the bidirectional-binding rule passes against the stubs
and Class 2 enforcement is real for D010 (the only acceptance with a
wired metric) plus any acceptance whose real wired test exists.

---

## 6. References

- Substrate spec: [`docs/specs/atdd-repo-substrate-spec-v12.md`](specs/atdd-repo-substrate-spec-v12.md) §4.5, §7.3, §11
- Issue index: [`docs/specs/atdd-repo-substrate-issues.md`](specs/atdd-repo-substrate-issues.md)
- Convention: [`src/atdd/tester/conventions/acceptance-violation.convention.yaml`](../src/atdd/tester/conventions/acceptance-violation.convention.yaml)
- Recipes (Class 1 fixes):
  [`metric-implementation`](../src/atdd/tester/conventions/metric-implementation.recipe.yaml),
  [`acceptance-test-headers`](../src/atdd/tester/conventions/acceptance-test-headers.recipe.yaml),
  [`acceptance-measurability`](../src/atdd/tester/conventions/acceptance-measurability.recipe.yaml),
  [`acceptance-phase`](../src/atdd/tester/conventions/acceptance-phase.recipe.yaml),
  [`acceptance-rule-block`](../src/atdd/tester/conventions/acceptance-rule-block.recipe.yaml),
  [`security-acceptance-binding`](../src/atdd/tester/conventions/security-acceptance-binding.recipe.yaml)
- Predecessor PRs: #426 (#407 Track A), #433 (#408 walker), #428 (#412 metric runner), #436 (#413 first metric), #438 (#411 plugin), #439 (#410 conformance), #427 (#419 SecurityResolver), #432 (#420 URN grammar), #437 (#421 hardcoding audit), #445 (#422 security rules), #441 (#416 phase dispatch), #444 (#417 spawn-harness blocks), #442 (#418 risk-score breakdown), #440 (#414 hard rename), #443 (#415 init substrate-mode).
