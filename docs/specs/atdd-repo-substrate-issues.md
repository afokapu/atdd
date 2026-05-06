# ATDD Repo Substrate — Implementation Issues

> **Purpose**: ready-to-file GitHub issues for the substrate implementation per `atdd-repo-substrate-spec-v12.md`.
> **Format**: each issue is one markdown block; copy into `gh issue create --title "..." --body-file -` or paste into the GitHub web UI.

---

## Index

17 issues across 8 tracks, assignable to 6 parallel agents.

| # | Title | Track | Agent | Depends on |
|---|---|---|---|---|
| 1 | Add repo archetype and RuleMetadata substrate fields | A | 1 | — |
| 2 | Derive WMBT/train repo rules from acceptance URNs | A | 1 | #1 |
| 3 | Add repo rule discovery CLI commands | A | 1 | #2 |
| 4 | Add substrate conformance convention and validators | B | 2 | #1, #2 |
| 5 | Add harness-mode pytest plugin for acceptance-bound violations | C | 3 | #1, #2 |
| 6 | Add metric runner with two-root metric-function discovery | D | 4 | #1 |
| 7 | Add first toolkit metric: hardcoded_theme_map_literal_count | D | 4 | #6 |
| 8 | Rename `atdd urn` to `atdd repo` and migrate references | E | 5 | #2 |
| 9 | Extend `atdd init` for consumer-repo substrate mode | E | 5 | #5, #8 |
| 10 | Add coach phase dispatch for repo rules | F | merge | #2, #5, #6, #8 |
| 11 | Add spawn-harness repo rule blocks | F | merge | #2 |
| 12 | Add repo archetype risk-score breakdown | F | merge | #2 |
| 13 | SecurityResolver + registration + graph edges | G | 6 | — |
| 14 | URN grammar validator + parent-it-belongs-to convention update | G | 6 | — |
| 15 | URN-prefix hardcoding audit and report | G | 6 | #13, #14 |
| 16 | Security-derived repo rules and reference-binding runner | H | 6 | #13, #14, #5, #6 |
| 17 | Substrate end-to-end validation (worked example) | I | merge | #1–#9 |

---

## Track A — Rule registry substrate (Agent 1)

### Issue #1 — Add repo archetype and RuleMetadata substrate fields

**Labels**: `substrate`, `track-a`, `wave-s0`

**Scope**

Implements §3.1 archetype extension and §4.1 RuleMetadata extension from `atdd-repo-substrate-spec-v12.md`.

- Edit `SPEC-COACH-RULEID-0002` to add `repo` to the archetype set.
- Edit `src/atdd/coach/conventions/rule-id.convention.yaml::domains` to register `repo`.
- Update `test_rule_id_uniqueness.py` to recognize `repo` as a valid archetype.
- Extend `RuleMetadata` (in `src/atdd/coach/utils/rule_binding.py`) with the substrate-added fields per §4.1:
  - Discriminator/resolution fields: `acceptance_urn`, `wmbt_urn`, `train_urn`, `security_urn`, `feature_urn`, `bound_acceptance_urn`, `phase`.
  - Context fields: `harness_type`, `harness_category`, `signal_metric`, `signal_threshold`, `given`, `when`, `then`, `author`, `created`. (Decision point in S0.2: keep on RuleMetadata vs. sidecar RuleContext object.)
- All new fields default to `None`; existing rules unaffected (non-breaking addition).

**Acceptance criteria**

- `bind_rule("repo.example.test")` does not raise on archetype validation.
- `RuleMetadata` instances for toolkit rules have all substrate-added fields equal to `None`.
- `test_rule_id_uniqueness.py` passes with the new archetype value.
- Unit test demonstrating constructable `RuleMetadata` with all substrate fields populated.

**Dependencies**: None — entry point of the substrate implementation.

**References**: §3.1, §4.1 of the spec.

---

### Issue #2 — Derive WMBT/train repo rules from acceptance URNs

**Labels**: `substrate`, `track-a`, `wave-s0`

**Scope**

Implements §3.3 rule-ID derivation, §4.2 field population, §4.3 walker plugin, §4.4 walker-set disposition.

- Extend the registry walker (`find_convention_files` in `src/atdd/coach/utils/rule_binding.py` or a new `find_repo_rules` peer) to walk:
  - `<repo>/plan/<wagon>/<id>.yaml` (WMBT acceptances) via `AcceptanceResolver`.
  - `<repo>/plan/_trains/<train-id>.yaml` (train acceptances) via `AcceptanceResolver`.
- For each acceptance, derive the rule-ID per §3.3 (`acc:<wagon>:<id>-<...>` → `repo.<wagon>.<id>-acc-<...>`).
- Populate `RuleMetadata` per §4.2 acceptance table:
  - `severity = 4` (constant, walker-set).
  - `disposition = "strict"` (constant, walker-set per §4.4).
  - `description` from `identity.purpose`.
  - `fix_hint` composed from `then.abstract` joined with `; `.
  - `validator` from `harness.type` (anchored test) or signal-mode runner.
  - `phase` from `identity.phase`.
  - All other passthrough fields per §4.2.
- Reject any YAML containing `disposition:` field (substrate enforcement at registry-build time — fail loudly).
- Reject acceptances whose `acc:` URN doesn't match `SPEC-COACH-RULEID-0001` grammar after derivation.

**Acceptance criteria**

- A real WMBT YAML (`plan/govern_lifecycle/D010.yaml`) produces derived rules in the registry with correct `RuleMetadata`.
- A real train YAML produces derived rules in the registry with correct `RuleMetadata`.
- `bind_rule("repo.govern-lifecycle.D010-acc-unit-001")` returns metadata with `description == "A single get_theme_map(config) helper..."`.
- A YAML with `disposition: advisory` declared produces a registry-build error pointing at the offending file.
- Integration test: walker finds N WMBT acceptances and M train acceptances in the toolkit's own `plan/`.

**Dependencies**: #1 (archetype + RuleMetadata extension must be in).

**References**: §3.3, §4.2, §4.3, §4.4 of the spec.

---

### Issue #3 — Add repo rule discovery CLI commands

**Labels**: `substrate`, `track-a`, `wave-s0`

**Scope**

Implements §9.2 CLI extensions for repo rule discovery.

- Verify `atdd rules show <id>`, `atdd rules where <id>`, `atdd rules grep <pattern>` work transparently for repo-archetype rules (no CLI changes expected — they call `bind_rule()` which now sees repo rules per #2).
- Add `atdd repo wmbt-rules <wmbt-urn>` listing all derived rules for a WMBT.
- Add `atdd repo train-rules <train-urn>` listing all derived rules for a train.
- Add `atdd repo rules` listing all repo rules with parent URN and rule-ID.
- (Note: `atdd repo` is the renamed `atdd urn`; until #8 lands, these subcommands live under `atdd urn`.)

**Acceptance criteria**

- `atdd urn rules` (or `atdd repo rules` post-#8) lists all derived rules from `plan/`.
- `atdd urn wmbt-rules wmbt:govern-lifecycle:D010` lists all rules derived from D010.
- `atdd rules show repo.govern-lifecycle.D010-acc-unit-001` returns the full RuleMetadata.
- `atdd rules grep "theme_map"` returns the rule.
- Unit tests for each subcommand.

**Dependencies**: #2 (registry must contain repo rules).

**References**: §9.1, §9.2 of the spec.

---

## Track B — Conformance validators (Agent 2, starts after #1, #2)

### Issue #4 — Add substrate conformance convention and validators

**Labels**: `substrate`, `track-b`, `wave-s0`

**Scope**

Implements §7.3 substrate enforcement convention with five rules and recipes.

- Create `src/atdd/tester/conventions/acceptance-violation.convention.yaml` per §7.3 with the five rules:
  - `tester.acceptance-violation.acceptance-must-be-measurable`
  - `tester.acceptance-violation.acceptance-must-declare-phase`
  - `tester.acceptance-violation.disposition-must-not-be-declared`
  - `tester.acceptance-violation.validator-binding-must-be-bidirectional`
  - `tester.acceptance-violation.metric-implementation-must-exist` (two-root lookup)
- Implement the validators:
  - `src/atdd/tester/validators/test_acceptance_measurable.py::test_every_acceptance_has_enforcement`
  - `src/atdd/tester/validators/test_acceptance_phase.py::test_every_acceptance_declares_phase`
  - `src/atdd/tester/validators/test_acceptance_disposition.py::test_no_disposition_in_repo_yaml`
  - `src/atdd/tester/validators/test_repo_validator_binding.py::test_validator_binding_is_bidirectional`
  - `src/atdd/tester/validators/test_metric_implementation.py::test_every_signal_metric_has_compute_function` (checks both repo-local `<repo>/.atdd/metrics/<metric>.py` and toolkit-shipped `src/atdd/runners/metrics/<metric>.py`).
- Create the five recipes:
  - `acceptance-measurability.recipe.yaml`
  - `acceptance-phase.recipe.yaml`
  - `acceptance-rule-block.recipe.yaml`
  - `acceptance-test-headers.recipe.yaml`
  - `metric-implementation.recipe.yaml`

**Acceptance criteria**

- `atdd repo validate` (or `atdd urn validate` pre-#8) fires the five rules with correct rule-IDs on intentionally broken fixtures.
- Each rule's failure output includes its recipe pointer.
- A fixture WMBT missing `harness.type` and `signal.metric` fails `acceptance-must-be-measurable`.
- A fixture WMBT missing `identity.phase` fails `acceptance-must-declare-phase`.
- A fixture WMBT containing `disposition: advisory` fails `disposition-must-not-be-declared`.
- A fixture with `signal.metric: foo` and no `foo.py` in either root fails `metric-implementation-must-exist`.

**Dependencies**: #1 (archetype), #2 (RuleMetadata population for fixtures).

**References**: §7.3, §11 (Class 1 day-1 failures) of the spec.

---

## Track C — Harness-mode pytest plugin (Agent 3, starts after #1, #2)

### Issue #5 — Add harness-mode pytest plugin for acceptance-bound violations

**Labels**: `substrate`, `track-c`, `wave-s0`

**Scope**

Implements §4.5 harness-mode runner and §7.2 pytest plugin.

- Implement the substrate's pytest plugin:
  - `pytest_collection_modifyitems`: for every test module under the configured test root, read `# URN: test:...`, `# Acceptance: ...`, `# WMBT: ...` / `# Train: ...`, `# Phase: ...`, `# Layer: ...` headers via `TestResolver`.
  - For each anchored test function: derive the rule-ID per §3.3, call `bind_rule()` to fetch metadata, attach to the pytest item.
  - At test execution: wrap with an interception hook. On `AssertionError`, construct a `Violation` (rule_id from binding, severity from registry, location from frame, detail from assertion message) and route through `assert_disposition_satisfied()`.
- Support N-to-1 binding (multiple anchored tests per acceptance per `EdgeType.TESTED_BY`): each failing test produces its own gate call/failure block.
- Plugin distribution: discoverable as a pytest entry-point via existing toolkit packaging conventions.

**Acceptance criteria**

- A pytest test with `# Acceptance: acc:foo:D003-unit-001` and `assert False` produces a Violation with `rule_id = repo.foo.D003-acc-unit-001` and routes through the gate.
- Two tests anchored to the same acceptance both run; each failing one produces its own gate call.
- A test without anchor headers does not produce substrate violations (just normal pytest behavior).
- Unit test demonstrating the plugin's hook integration.
- Integration test: against a fixture WMBT with three acceptances and three anchored tests, all three runs are observed by the substrate.

**Dependencies**: #1 (RuleMetadata), #2 (registry walker).

**References**: §4.5 (harness section), §7.2 of the spec.

---

## Track D — Metric runner (Agent 4, starts after #1)

### Issue #6 — Add metric runner with two-root metric-function discovery

**Labels**: `substrate`, `track-d`, `wave-s0`

**Scope**

Implements §4.5 metric-mode runner and metric-function registry.

- Implement `test_metric_runner::test_metric_threshold_satisfied` (registry-iterating runner):
  - Iterates over every rule in the registry where `signal_metric` and `signal_threshold` are populated.
  - For each, looks up the metric module via two-root lookup:
    1. **Repo-local first**: `<repo>/.atdd/metrics/<metric>.py::compute` (consumer-authored, wins on collision).
    2. **Toolkit fallback**: `src/atdd/runners/metrics/<metric>.py::compute` (toolkit-shipped commons).
  - Calls `compute(repo_root) -> int | float | bool`.
  - Calls `passes(value, threshold) -> bool` from the same module to determine pass/fail.
  - On `passes() == False`, constructs Violation and routes through gate as `validator_id="test_metric_runner::test_metric_threshold_satisfied"`.
- Define module contract for metric implementations:
  - Required: `compute(repo_root: Path) -> int | float | bool`
  - Required: `passes(value, threshold) -> bool` (default behavior: `value <= threshold` for upper-bound metrics; minimum-requirement metrics MUST override).
- Document the threshold-direction discipline: default `<=` is upper-bound; minimum-requirement metrics override.
- Plugin must coexist with #5: when an acceptance has both `harness.type` and `signal.metric`, both runners produce independent gate calls.

**Acceptance criteria**

- A fixture WMBT with `signal.metric: foo` and `signal.threshold: 0` plus a fixture `<repo>/.atdd/metrics/foo.py` returning `compute() == 5` produces a Violation.
- Repo-local metric overrides toolkit-shipped metric of the same name.
- Missing metric file fires `metric-implementation-must-exist` (#4 ships the rule; this issue tests it works end-to-end).
- A metric with custom `passes(value, threshold) -> value >= threshold` works correctly for minimum-requirement use case.
- Both-mode test: a fixture acceptance with both harness and signal produces violations through both runners independently.

**Dependencies**: #1 (RuleMetadata).

**References**: §4.5 (metric section) of the spec.

---

### Issue #7 — Add first toolkit metric: hardcoded_theme_map_literal_count

**Labels**: `substrate`, `track-d`, `wave-s1`

**Scope**

The toolkit dogfoods the substrate via `plan/govern_lifecycle/D010.yaml` which declares `signal.metric: hardcoded_theme_map_literal_count`. This issue ships the implementation.

- Implement `src/atdd/runners/metrics/hardcoded_theme_map_literal_count.py`:
  - `compute(repo_root: Path) -> int`: count `theme_map` dict literals outside `coach/utils/theme_map.py` via AST traversal of `src/atdd/`.
  - `passes(value, threshold) -> bool`: default (`value <= threshold`) — appropriate since 0 is the goal.

**Acceptance criteria**

- Running `pytest` against the toolkit invokes the metric runner (#6) for D010's acceptance.
- If the toolkit has 0 hardcoded `theme_map` literals, the rule passes.
- If a test fixture introduces a hardcoded literal, the rule fails with rule-IDed feedback.
- Used as the canonical "first metric" example for documentation and onboarding.

**Dependencies**: #6 (metric runner must exist).

**References**: §4.5, §7.3 (metric-implementation-must-exist), §11 (worked example).

---

## Track E — CLI / init (Agent 5, starts after #2)

### Issue #8 — Rename `atdd urn` to `atdd repo` and migrate references

**Labels**: `substrate`, `track-e`, `wave-s0`, `breaking-change`

**Scope**

Implements §9.1 hard CLI rename.

- Rename CLI module from `atdd urn` to `atdd repo`. Subcommands stay the same:
  - `atdd urn graph` → `atdd repo graph`
  - `atdd urn validate` → `atdd repo validate`
  - `atdd urn orphans` → `atdd repo orphans`
  - `atdd urn broken` → `atdd repo broken`
- Add new subcommands:
  - `atdd repo rules`
  - `atdd repo wmbt-rules <wmbt-urn>`
  - `atdd repo train-rules <train-urn>`
- (`atdd repo security-rules` lands in #16.)
- Migrate all toolkit-side references via `grep -rn "atdd urn"`:
  - Documentation (README, CONTRIBUTING, etc.)
  - Generated agent prompts (CLAUDE.md, AGENTS.md)
  - Recipes referencing the command
  - Internal scripts and CI config
  - Test fixtures
- Add CHANGELOG entry with sed-friendly migration: `sed -i 's/atdd urn/atdd repo/g' <files>` for downstream consumers.
- No backward-compat alias — hard rename per design decision.

**Acceptance criteria**

- `atdd repo --help` lists all subcommands.
- `atdd urn <anything>` exits with a clear "renamed to atdd repo" error message.
- `grep -rn "atdd urn" src/ docs/` returns zero matches in toolkit-authored content.
- CHANGELOG entry includes the migration command.

**Dependencies**: #2 (so the new `atdd repo rules` subcommands have data to query).

**References**: §9.1 of the spec.

---

### Issue #9 — Extend `atdd init` for consumer-repo substrate mode

**Labels**: `substrate`, `track-e`, `wave-s0`

**Scope**

Implements §9.3 atdd init extension.

- Detect mode by heuristic with explicit flag override:
  - Default: presence of `plan/` AND absence of `src/atdd/` → consumer-repo mode.
  - `--consumer-repo` flag: force consumer-repo mode regardless of heuristic.
  - `--toolkit` flag: force toolkit mode (no substrate registration).
- In consumer-repo mode:
  - Update `.atdd/config.yaml` with substrate fields: `repo.test_root`, etc.
  - Register the substrate's pytest plugin (from #5) via the toolkit's existing pytest-plugin mechanism.
- Document the toolkit-self-application case in CONTRIBUTING.md (run `atdd init --consumer-repo` against the toolkit's own repo to dogfood the substrate against `plan/govern_lifecycle/`).

**Acceptance criteria**

- Running `atdd init` in a directory with `plan/` and no `src/atdd/` registers the pytest plugin and updates config.
- Running `atdd init --toolkit` in the same directory does NOT register the plugin.
- Running `atdd init --consumer-repo` in any directory registers the plugin.
- `atdd init` is idempotent — running it twice produces no diff on the second run.
- CONTRIBUTING.md documents the dogfooding case.

**Dependencies**: #5 (pytest plugin must exist), #8 (CLI rename complete so init's docs reference current names).

**References**: §9.3 of the spec.

---

## Track F — Coach integration (merge-window, after C+D+E)

### Issue #10 — Add coach phase dispatch for repo rules

**Labels**: `substrate`, `track-f`, `wave-s2`, `coach`

**Scope**

Implements §8.1 phase-driven dispatch.

- Coach selects validators per phase by reading `RuleMetadata.phase` (canonical), not by source kind.
- For each coach phase, the validator set is:
  - Toolkit validators for that phase.
  - All repo rules whose `RuleMetadata.phase` matches the current coach phase, regardless of source kind.
- REFACTOR phase additionally sweeps every strict-disposition rule from both registries.
- RED-vs-GREEN expectation handling: substrate emits violations regardless of phase; coach interprets per phase (RED = expected, GREEN = not). Already coach v6 §4.1 behavior; document the integration.

**Acceptance criteria**

- A coach session at GREEN selects all repo rules with `phase: GREEN`.
- A coach session at RED selects all repo rules with `phase: GREEN` (the ATDD convention) and treats their violations as expected.
- Integration test against a real WMBT with multiple acceptances at different phases.

**Dependencies**: #2 (registry), #5 (harness runner), #6 (metric runner), #8 (CLI rename).

**References**: §8.1 of the spec, coach v6 §6.5.

---

### Issue #11 — Add spawn-harness repo rule blocks

**Labels**: `substrate`, `track-f`, `wave-s2`, `coach`

**Scope**

Implements §8.2 spawn-harness extensions.

- Extend coach v6's spawn-harness renderer to emit `wmbt_rules:`, `train_rules:`, and `security_rules:` blocks (security_rules block wired in #16).
- Each block lists rules whose `phase` matches the current coach phase, scoped per §8.1.
- Use the structure shown in §8.2 of the spec.

**Acceptance criteria**

- Spawning a coder agent at GREEN includes the `wmbt_rules:` block listing all GREEN-phase WMBT rules touched by the diff.
- Spawning a coder at SMOKE includes `train_rules:` for trains in scope (per §8.4).
- Format matches the spec example exactly.

**Dependencies**: #2 (registry).

**References**: §8.2 of the spec, coach v6 §7.1.

---

### Issue #12 — Add repo archetype risk-score breakdown

**Labels**: `substrate`, `track-f`, `wave-s2`, `coach`

**Scope**

Implements §8.3 risk-score archetype breakdown.

- Coach v6 §6.8 computes risk score as sum of severity over active violations. Extend the breakdown to include a `repo:` slice (sum of severity of repo-archetype violations), separate from toolkit slices.
- Surface the `repo:` slice in PR descriptions per coach v6's PR template.

**Acceptance criteria**

- A coach run with a mix of toolkit and repo violations shows separate slices in the risk score output.
- PR description includes the breakdown.

**Dependencies**: #2.

**References**: §8.3 of the spec, coach v6 §6.8.

---

## Track G — Security Workstream A (Agent 6, independent)

### Issue #13 — SecurityResolver + registration + graph edges

**Labels**: `substrate`, `track-g`, `workstream-a`, `security`

**Scope**

Workstream A items A.1, A.2, A.5 consolidated into one cohesive toolkit upgrade.

- Add `SecurityResolver` class to `src/atdd/coach/utils/graph/resolver.py`:
  - Reads `feature.yaml::security.abuse_cases[]`.
  - Emits `security:<wagon>:<feature-slug>:<threat-seq>` URNs.
- Register `SecurityResolver` in `ResolverRegistry` so graph queries, `atdd repo validate`, and the substrate walker all see security URNs.
- Update `GraphBuilder` with edges: `feature → security` (CONTAINS), `security → acceptance` (REFERENCES via `acceptance_ref`).
- Add unit tests for resolver and graph integration.

**Acceptance criteria**

- A test fixture `feature.yaml` with `security.abuse_cases[]` produces resolved `security:` URNs.
- Graph integration test: edges exist as described.
- `atdd repo validate` reports broken `acceptance_ref` URNs in abuse_cases.

**Dependencies**: None — independent of the rest of the substrate.

**References**: §10.0 Workstream A (A.1, A.2, A.5) of the spec.

---

### Issue #14 — URN grammar validator + parent-it-belongs-to convention update

**Labels**: `substrate`, `track-g`, `workstream-a`

**Scope**

Workstream A items A.3 and A.4.

- Update the URN grammar validator to accept three-segment `security:` URNs.
- Apply the parent-it-belongs-to principle (§3.2) so future resource types can register multi-segment URNs without further validator changes.
- Document the principle in `src/atdd/coach/conventions/rule-id.convention.yaml` (or wherever toolkit URN structure is documented). Include the §3.2 table showing per-resource segment counts.

**Acceptance criteria**

- URNs of form `security:<wagon>:<feature-slug>:<threat-seq>` validate as well-formed.
- URNs violating the parent-it-belongs-to principle (e.g., wrong segment count for a known resource type) fail validation with a clear error.
- Convention documentation includes the per-resource segment-count table.

**Dependencies**: None.

**References**: §3.2 of the spec, §10.0 Workstream A (A.3, A.4).

---

### Issue #15 — URN-prefix hardcoding audit and report

**Labels**: `substrate`, `track-g`, `workstream-a`

**Scope**

Workstream A item A.6.

- Audit toolkit code for hardcoded URN-prefix lists, resolver enumerations, URN-aware test fixtures.
- Update any found to be open-ended (use the registry, not closed enumerations).
- Produce written audit report at `docs/urn-prefix-audit-2026.md` listing every code site searched, every hardcoded list found, every fix made.
- Empty-handed audits are acceptable but must produce the report.

**Acceptance criteria**

- Audit report exists in the documented location.
- Report enumerates all searched code sites.
- All findings listed with PR references for fixes.
- After landing: introducing a new URN type (e.g. dummy `theatre:` for testing) does not require code changes outside resolver/registry.

**Dependencies**: #13, #14 (so the audit can verify both work end-to-end).

**References**: §10.0 Workstream A (A.6) of the spec.

---

## Track H — Security substrate (Agent 6, after Workstream A)

### Issue #16 — Security-derived repo rules and reference-binding runner

**Labels**: `substrate`, `track-h`, `wave-s3`, `security`

**Scope**

Implements §4.5 security-mode runner, §7.4 reference-binding enforcement, §7.3 security enforcement rule, and security CLI subcommand. Consolidates S3.1 through S3.5 into one issue because they are tightly coupled.

- Extend the registry walker (#2) to consume `feature.yaml::security.abuse_cases[]` via `SecurityResolver` (#13). Adds `security_urn`, `feature_urn`, `bound_acceptance_urn` to `RuleMetadata` for security-derived rules.
- Map `abuse_case.severity` to integer (low→2, medium→3, high→4, critical→5).
- Add the substrate enforcement rule `tester.acceptance-violation.security-rule-must-have-acceptance-ref-resolved` (#4 shipped the others; this one belongs to S3 because it depends on `SecurityResolver`).
- Implement `test_security_ref_binding::test_acceptance_ref_resolves_and_passes`:
  - Iterates registry for security rules with populated `bound_acceptance_urn`.
  - Reads session result map (`session._atdd["rule_outcomes"]`) for the bound acceptance's outcome.
  - Emits Violation if bound acceptance's rule failed.
- Implement pytest hook ordering:
  - `pytest_collection_modifyitems`: reorders security items after acceptance items via `@pytest.mark.atdd_phase("security")`.
  - `pytest_runtest_logreport`: populates `session._atdd["rule_outcomes"]` keyed by rule_id.
- Add `security_rules:` block to coach spawn-harness (#11 shipped wmbt/train; this completes the trio).
- Add `atdd repo security-rules <feature-urn>` CLI subcommand.

**Acceptance criteria**

- A fixture feature.yaml with one resolved abuse_case and a passing bound acceptance produces no security violation.
- Same fixture but with a failing bound acceptance produces a security violation referencing the threat name and mitigation.
- An unresolved `bound_acceptance_urn` is caught by the validation-time enforcement rule (not the runtime runner).
- Session ordering: bound acceptance test outcomes are recorded before security runner reads.
- Spawn-harness security block matches the §8.2 example.

**Dependencies**: #13, #14 (Workstream A), #5 (harness plugin for the test ordering pattern), #6 (metric runner — to ensure plugin coexistence works for all three runners).

**References**: §4.5 (security section), §7.3, §7.4, §8.2 of the spec.

---

## Track I — Integration acceptance (merge, after all)

### Issue #17 — Substrate end-to-end validation (worked example)

**Labels**: `substrate`, `track-i`, `wave-s1`, `integration`

**Scope**

This is the substrate's done-line, not just an example. Implements §11 day-1 experience as the integration acceptance for issues #1–#9 (and optionally #10–#12 if coach integration is in scope for this milestone).

- Pick one WMBT and one train from the toolkit's plan/.
- Confirm acceptances have the required fields (`identity.phase`, `harness.type` and/or `signal.metric+threshold`).
- Confirm anchored tests have correct headers.
- Run `atdd repo validate` and observe substrate Class 1 enforcement firing on any gaps. Fix until clean.
- Run pytest and observe Class 2 (real contract) failures use the substrate's enriched failure output.
- Document the worked example in the repository.

**Acceptance criteria**

- A running coach session uses substrate failure output for a real contract violation in the chosen WMBT.
- An agent (human or LLM) works through a Class 1 substrate-conformance failure using the recipe pointer.
- An agent works through a Class 2 contract failure using the description + fix_hint composed from existing acceptance fields.
- `atdd repo validate` passes with zero substrate-conformance failures on the toolkit's own `plan/`.
- The worked example is documented in `docs/substrate-worked-example.md`.

**Dependencies**: #1–#9 (substrate must be functionally complete). Optional: #10–#12 if validating against real coach.

**References**: §10.1 S1, §11 of the spec.

---

## Filing notes

- All issues should reference the spec at `atdd-repo-substrate-spec-v12.md` for context.
- Each issue's "Dependencies" section is the merge-order constraint, not a soft suggestion.
- Track F (coach integration) is intentionally not assigned to a dedicated agent; it's a merge-window task after C/D/E land. Agent 1 or Agent 3 can pick up F's three issues during integration.
- Track I (#17) is the substrate's done-line. Until #17 passes, the substrate is not done — even if all upstream issues are individually closed.
- Workstream A (#13–#15) can run fully in parallel with all other tracks; it gates Track H but not the rest.
- Hard rename (#8) has a one-time downstream cost for any consumer-repo CI configs that reference `atdd urn`. Document in the toolkit CHANGELOG with a sed migration command.
