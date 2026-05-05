# ATDD Repo Rule-ID Substrate — Spec

> **Status**: Ready for implementation.
> **Companion to**: `atdd-coach-spec-v6.md`.

---

## 1. Why this exists

The toolkit's rule-ID system gives toolkit code five things consumer repos should also get:

1. Stable IDs for every testable claim, resolvable via `bind_rule()`.
2. Structured `Violation` records instead of bare pytest prose.
3. Disposition-driven CI behavior per rule.
4. Inline suppression markers with `UNTIL=` deadlines.
5. **Enriched failure output** — `description:` and `fix_hint:` surfaced above each violation block (toolkit commit `9b4da09`).

Consumer repos already have the structural raw material:

- WMBTs declare acceptance criteria for unit-level contracts (drive RED/GREEN/REFACTOR).
- Trains declare acceptance criteria for integration flows (drive SMOKE/E2E).
- Features declare security threats via `feature.yaml::security.abuse_cases[]` (drive cross-phase security verification).

And consumer repos already have anchoring infrastructure:

- `atdd repo` (the URN graph command) walks `plan/`, resolves `wagon:` / `feature:` / `wmbt:` / `acc:` / `train:` / `test:` URNs, and validates the relationships.
- `TestResolver` parses `# URN: test:...` headers and `# Acceptance:`, `# WMBT:`, `# Train:`, `# Phase:`, `# Layer:` metadata lines from test files.
- `GraphBuilder` wires test ↔ acceptance ↔ WMBT ↔ wagon ↔ train edges.

The substrate makes WMBT, train, and security rules contribute to the same `bind_rule()` registry, derives rule-IDs mechanically from the existing URN graph, and reuses the existing test-anchoring conventions.

The agent payoff: instead of "AssertionError: expected X, got Y" the agent sees the canonical rule, what the contract requires, and the structured expectations that prove it.

---

## 2. Architectural principles

**One substrate, multiple registry sources.** Toolkit and repo rules share `bind_rule()`, `Violation`, the disposition gate, the suppression scanner, and the enriched failure output.

**Reuse the URN graph.** Tests anchor to acceptances via existing header comments. Acceptances live in WMBT/train YAMLs reachable through `AcceptanceResolver`. Security artifacts live in `feature.yaml` reachable through `SecurityResolver`. Rule-IDs derive from these URNs mechanically.

**Repo namespace via fixed archetype.** Consumer rules use `repo.*` prefix. `coder|coach|tester|planner` remain toolkit-only.

**Conventions are toolkit artifacts.** Consumer repos contribute rules exclusively through structured plan-folder content. If a behavior needs enforcing across consumer repos, the toolkit declares the convention.

**No new acceptance YAML fields.** The substrate consumes what's already in the WMBT/train/feature schemas. Severity, description, validator, mode, phase — all come from existing fields.

**Living plan = living rules.** A WMBT, train, or feature file in `plan/` is a live rule source. Delete the file → its rules leave the registry on next walk. No archive, no tombstones, no promotion.

**Plan ≠ convention.** WMBTs, trains, and features share *mechanics* with conventions (rule-ID grammar, Violation emission, disposition gate) but are their own kind of artifact.

**Identical failure output.** Repo-rule failures use the same `_format_failure_block` / `_format_advisory_block` path that toolkit-rule failures use. Zero new code paths in the formatter; descriptions and fix-hints compose from existing YAML fields.

**Acceptance rules describe contracts, not implementations.** What the rule requires is the contract; how it gets satisfied is the agent's domain modeling work. The substrate's failure output reflects the contract (purpose + expectations), not implementation guidance.

**Phase-scoped enforcement, driven by `identity.phase`.** Each acceptance declares its phase explicitly via `identity.phase`. Coach reads this per rule and runs only the rules whose declared phase matches the current coach phase. Source kind (WMBT vs train vs security) informs scoping — which rules coach considers — but `identity.phase` is canonical for which considered rules actually apply now.

**Strict from day 1.** Acceptance-derived rules are strict by construction (the contract holds or the work isn't done). Substrate enforcement rules fire on non-compliant repos with rule-IDed feedback and recipe pointers.

**Repo contract rules are unsuppressible.** Acceptance-derived and security-derived rules carry `disposition: strict` by construction (set by the registry walker, not declared in YAML). Suppression markers (`# atdd:suppress(...)`) are ineffective against strict rules — the toolkit's `assert_disposition_satisfied` gate appends failures unconditionally for strict disposition without consulting the suppression scanner. A failing acceptance cannot be silenced; tightening or relaxing a contract happens by editing the WMBT/train/feature YAML, with the graph chain (code, test) updating accordingly.

**Prioritization driven by rule kind.** For acceptance rules, severity is a constant 4 (correctness — the contract failed) and the WMBT lifecycle ensures failures surface and get fixed; no per-rule prioritization needed. For security rules, severity is preserved from the abuse_case YAML where the planner is rating an external concern (low/medium/high/critical, mapped to 2..5). Severity drives risk-score weighting and human-escalation queue ordering, NOT enforcement strictness — all security rules are strict regardless of severity, because the abuse_case is itself a deliberate authoring decision (the planner made the threat explicit; therefore mitigation is required even when severity is low).

---

## 3. Grammar

### 3.1 Archetype extension

`SPEC-COACH-RULEID-0001` grammar unchanged:

```
RULE_ID    ::= <archetype> "." <convention_short_name> "." <rule_name>
```

`SPEC-COACH-RULEID-0002` archetype set extends by one value:

```
archetype  ::= coder | coach | tester | planner | repo
```

### 3.2 URN segment count: parent-it-belongs-to principle

Each URN takes the form `<resource>:<parent-coordinates>:<local-id>`, where `<parent-coordinates>` may require multiple colon-separated tokens depending on how the parent is uniquely identified. URN segment count reflects the parent's identification cost — it is not a fixed scheme depth.

| Resource | Parent | Form |
|---|---|---|
| `wagon:<id>` | none | `wagon:auth` |
| `train:<id>` | none | `train:checkout-train` |
| `feature:<wagon>:<slug>` | wagon (1 token) | `feature:auth:session-management` |
| `wmbt:<wagon>:<wmbt-id>` | wagon (1 token) | `wmbt:auth:D003` |
| `acc:<wagon>:<wmbt-id>-<harness>-<seq>` | WMBT (collapses into local-id segment) | `acc:auth:D003-UNIT-001-token-rotation` |
| `security:<wagon>:<feature-slug>:<threat-seq>` | feature (2 tokens) | `security:auth:session-management:001` |

`security:` URNs take three segments because their parent is a feature, and features are uniquely identified by `<wagon>+<feature-slug>`. Parent coordinates inflate the URN's segment count, naturally and consistently.

### 3.3 Rule-ID derivation

Rule-IDs derive mechanically from URNs. The rule's `id:` field is forbidden in any acceptance/security YAML — derivation is the only path.

| Source URN | Derived rule-ID |
|---|---|
| `acc:<wagon>:<wmbt-id>-<harness>-<seq>` | `repo.<wagon>.<wmbt-id>-acc-<harness>-<seq>` |
| `acc:<train>:<acceptance-slug>` | `repo.<train>.acc-<acceptance-slug>` |
| `security:<wagon>:<feature-slug>:<threat-seq>` | `repo.<wagon>.<feature-slug>-security-<seq>` |

The `acc-` and `security-` infixes in the rule-name segment make the source self-evident at any callsite.

For toolkit conventions, the rule's `id:` is declared explicitly (existing behavior, unchanged).

---

## 4. Registry sources

The walker reads from four classes of sources, in defined order:

1. **Toolkit conventions** (existing): installed package's `*.convention.yaml` files. Includes the substrate's enforcement rules under the `tester` archetype (§7.3).
2. **WMBT acceptance rules** (new): `<repo>/plan/<wagon>/<id>.yaml`. Each acceptance contributes a rule, derived from its `acc:` URN.
3. **Train acceptance rules** (new): `<repo>/plan/_trains/<train-id>.yaml`. Each acceptance contributes a rule.
4. **Security artifact rules** (new, gated on toolkit prerequisite — see §10.0): `<repo>/plan/<wagon>/features/<feature>.yaml::security.abuse_cases[]`. Each abuse case contributes a rule, derived from its `security:` URN.

Cross-source collisions raise the existing `AmbiguousRuleError`. Toolkit ↔ repo collisions are impossible by archetype.

### 4.1 RuleMetadata extension

The substrate extends `RuleMetadata` with two field categories:

**Discriminator and resolution fields** (consumed by the gate, the walker, and rule-discovery commands):

```python
@dataclass(frozen=True)
class RuleMetadata:
    # ... existing fields including severity, disposition, description, fix_hint, validator ...

    # Acceptance / security URN discriminators (added by the substrate)
    acceptance_urn: Optional[str] = None
    wmbt_urn: Optional[str] = None
    train_urn: Optional[str] = None
    security_urn: Optional[str] = None
    feature_urn: Optional[str] = None       # security rules only
    bound_acceptance_urn: Optional[str] = None  # security rules only — was acceptance_ref in YAML
    phase: Optional[str] = None             # the canonical dispatch field per §8.1
```

Exactly zero or one of `wmbt_urn` / `train_urn` / `security_urn` is populated. `acceptance_urn` is populated for acceptance-derived rules. `feature_urn` and `bound_acceptance_urn` are populated for security rules.

`bound_acceptance_urn` holds the URN of the acceptance the security rule binds to. It is named distinctly from `fix_hint_ref` (and from the YAML field `acceptance_ref`) to make explicit that it is a graph-resolvable URN, not an opaque pointer string.

**Context fields** are passthrough metadata used by spawn-harness rendering, reviewer prompts, and `atdd repo wmbt-rules`/`train-rules` listings. They are not consumed by the gate. The substrate may carry them on `RuleMetadata` directly or on a sidecar `RuleContext` object resolved at need; the choice is an implementation detail of issue #2. The fields are:

| Field | Source |
|---|---|
| `harness_type` | from `harness.type` |
| `harness_category` | from `harness.category` |
| `signal_metric` | from `signal.metric` (when present) |
| `signal_threshold` | from `signal.threshold` (when present) |
| `given` / `when` / `then` | from `given.abstract` / `when.abstract` / `then.abstract` (full lists) |
| `author` / `created` | from `metadata.author` / `metadata.created` |

For toolkit rules, all substrate-added fields are `None`. Non-breaking addition to the existing dataclass.

### 4.2 Field population for repo rules

The walker reads existing acceptance/security fields and populates `RuleMetadata` directly — no new YAML fields are required of the planner.

**Acceptance-derived rules (WMBT or train):**

| RuleMetadata field | Source |
|---|---|
| `rule_id` | derived from `acc:` URN per §3.3 |
| `severity` | constant 4 (high — correctness) |
| `disposition` | constant `strict`, set by walker (not declared in YAML; see §4.4) |
| `description` | from `identity.purpose` |
| `fix_hint` | composed from `then.abstract` items joined with `; ` (preserves enriched-output format with no new code path; long lists may produce long lines — acceptable today, formatter could later render as a bulleted block) |
| `validator` | Bidirectional `<module>::<function>` reference matching the toolkit's `RuleMetadata.validator` contract. For harness mode, the anchored test function (e.g. `test_pricing_funnel_step::test_on_accept_emits_step_accepted`). For signal mode, the toolkit-shipped metric runner (e.g. `test_metric_runner::test_metric_threshold_satisfied`) — see §4.5 for the runner pattern and the metric-function registry. When both modes are present (§5.3), each mode runs through its own validator and the gate sees them as independent calls. |
| `phase` | from `identity.phase` |
| `acceptance_urn` | from `identity.urn` |
| `wmbt_urn` or `train_urn` | from the parent YAML |

(Context fields — `harness_type`, `signal_metric`, `given/when/then`, etc. — populated per §4.1.)

**Security-derived rules:**

| RuleMetadata field | Source |
|---|---|
| `rule_id` | derived from `security:` URN per §3.3 |
| `severity` | mapped from `abuse_case.severity` (low→2, medium→3, high→4, critical→5) |
| `disposition` | constant `strict`, set by walker (see §4.4) |
| `description` | composed from `abuse_case.name` + `abuse_case.threat` |
| `fix_hint` | from `abuse_case.mitigation` |
| `validator` | Bidirectional `<module>::<function>` reference. The toolkit-shipped reference-binding runner (e.g. `test_security_ref_binding::test_acceptance_ref_resolves_and_passes`) — see §4.5. The runner consumes `bound_acceptance_urn` from `RuleMetadata` at execution time. Reference-binding mode (§7.4) — no per-rule test function is authored. |
| `security_urn` | from the abuse case's URN |
| `feature_urn` | from the parent feature YAML's URN |
| `bound_acceptance_urn` | from `abuse_case.acceptance_ref` (the acc: URN this threat is mitigated by) |

Acceptance rules have no recipe pointer. Recipes are prescriptive ("how to do this"), and acceptance rules describe contracts not implementations. The substrate's enforcement convention rules (§7.3) carry recipes because the convention IS the rule and prescription is correct there.

### 4.3 Walker plugs into existing resolvers

The walker uses `AcceptanceResolver` and `SecurityResolver` to enumerate URNs and their parent YAML files. For each URN:

1. Read the parent YAML.
2. Verify the acceptance declares `identity.phase` AND has either `harness.type` (with binding test) OR `signal.metric` + `signal.threshold` (both required together) — measurability and phase invariants (§7.3).
3. Derive the rule-ID per §3.3.
4. Construct `RuleMetadata` per §4.2.

Acceptances or abuse cases that fail any invariant don't contribute to the registry — they fire the substrate's enforcement rules instead.

### 4.4 Walker-set disposition

For repo-archetype rules (acceptance-derived and security-derived), `disposition` is set to `strict` by the walker, not declared in the YAML. Repo YAML must NOT include a `disposition:` field; the substrate's enforcement validator rejects YAML containing one (since it would be a misleading hint that the value is configurable).

This is a deliberate departure from the toolkit-convention pattern (where YAML declares disposition). The rationale: acceptance criteria and threat mitigations are by definition non-negotiable; making disposition declarable invites "soften this with `advisory`" patterns that erode contract semantics. Constant `strict` enforces the principle structurally.

For someone debugging the registry, `bind_rule(<repo-rule-id>).disposition` returns `strict` even though no YAML declared it. Tooling that revalidates "is disposition declared properly" against YAML source must allow for walker-set disposition on repo archetype.

### 4.5 Runners — uniform N-to-1 binding

All three substrate runners follow the same shape: N validations per rule, all must pass. The difference is *how* the N is determined.

| Runner | How N is determined | Source of truth |
|---|---|---|
| Harness mode | Tests anchored to the acceptance via `# Acceptance: <urn>` headers | `TestResolver` + `TESTED_BY` graph edge (existing toolkit) |
| Metric mode | Single computation per rule (N=1) | `signal.metric` field |
| Security mode | Single resolution per rule (N=1) | `bound_acceptance_urn` field |

For all three, each individual validation that fails produces its own gate call and failure block. The rule passes iff every validation passes.

**Harness-mode runner.** The toolkit's existing `TestResolver` already supports many tests anchored to a single acceptance — `EdgeType.TESTED_BY` is one-to-many. The substrate's pytest plugin (registered by `atdd init`) wraps each anchored test with the rule-bound emission hook described in §7.2. If three tests anchor to `acc:foo:D003-unit-001`, all three execute; each failing one produces a `Violation` and routes through the gate as `validator_id=<that_test's_module>::<that_test's_function>`. The acceptance's rule passes iff all three tests pass.

**Metric-mode runner (`test_metric_runner::test_metric_threshold_satisfied`)** ships in the toolkit and:

1. Iterates over every rule in the registry where `signal_metric` and `signal_threshold` are populated.
2. For each, looks up the metric's compute function in the **metric-function registry** (see below).
3. Calls `compute(repo_root) -> int | float | bool` to get the measured value.
4. Calls `passes(value, threshold) -> bool` from the same metric module to determine pass/fail. Default `passes` is `value <= threshold` for toolkit-shipped metrics; modules may override (e.g. `value >= threshold` for "at least N samples").
5. On `passes() == False`, constructs a `Violation` and calls `assert_disposition_satisfied(validator_id="test_metric_runner::test_metric_threshold_satisfied", violations=[...])` for that rule.

**Metric-function registry — two-root lookup.** Each named metric needs an actual compute function. The runner discovers metrics via filesystem walk in two roots, in precedence order:

1. **Repo-local**: `<repo>/.atdd/metrics/<metric>.py::compute` (consumer-authored). Wins on collision so consumers can override toolkit defaults.
2. **Toolkit-shipped**: `src/atdd/runners/metrics/<metric>.py::compute` (toolkit-shipped commons like `lines_of_code`, `cyclomatic_complexity`, etc.).

Each metric module exposes:

```python
def compute(repo_root: Path) -> int | float | bool: ...
def passes(value: <return_type_of_compute>, threshold: <scalar>) -> bool:
    return value <= threshold  # default; override per-metric as needed
```

**Threshold direction — default and override.** The default `passes` implementation treats `threshold` as an *upper bound*: the metric passes when the measured value is at or below threshold. This matches the common case for "count of violations should be at most N" metrics (e.g., `hardcoded_theme_map_literal_count` with `threshold: 0`).

Metrics representing *minimum requirements* (e.g., "at least N test cases", "coverage at least 80%") MUST override `passes` explicitly:

```python
def passes(value, threshold):
    return value >= threshold
```

The substrate does not infer direction from the metric name. The metric module owns the semantic. A rule declaring `threshold: 100` for a coverage metric without overriding `passes` would silently invert (it would require coverage ≤ 100% rather than ≥ 100%). Authors of minimum-requirement metrics are responsible for the override; reviewers and `atdd issue review` should sanity-check threshold direction at WMBT-authoring time.

A rule declaring `signal.metric: foo` requires `foo.py::compute` to exist in at least one of the two roots. Missing implementations fail the substrate's enforcement rule `metric-implementation-must-exist` (§7.3), which checks both roots before failing.

**Security-mode runner (`test_security_ref_binding::test_acceptance_ref_resolves_and_passes`)** ships in the toolkit and:

1. Iterates over every rule in the registry where `bound_acceptance_urn` is populated AND the URN resolved at registry-build time (unresolved refs are caught earlier by the validation-time enforcement rule, see §7.4).
2. For each, queries the **session result map** (see below) for the bound acceptance's outcome.
3. If the bound acceptance's rule was failing in this run, constructs a `Violation` and calls `assert_disposition_satisfied(validator_id="test_security_ref_binding::test_acceptance_ref_resolves_and_passes", violations=[...])` for that security rule.

**Run ordering and session result map.** The security runner depends on knowing whether bound acceptance rules passed *in this run*. Two pytest hooks provide this without inventing new toolkit state:

- `pytest_collection_modifyitems`: the substrate's pytest plugin reorders collected items so all security-mode runner items execute after all acceptance-mode runner items for the same phase. Implementation: a custom `pytest.mark` (`@pytest.mark.atdd_phase("security")`) applied to security-runner items, plus a sort step in the hook.
- `pytest_runtest_logreport`: populates a session-scoped namespace dict (`session._atdd: Dict[str, Any]`, with `session._atdd["rule_outcomes"]: Dict[str, Outcome]` keyed by `rule_id`). The outer container isolates substrate state from accidental collisions with other plugins. The dict is written by the disposition gate as part of its existing flow (the gate already knows the rule_id; this hook just records the outcome alongside).

The security runner reads the session dict at execution time. Because `pytest_collection_modifyitems` guarantees acceptance runners executed first, every bound acceptance's outcome is recorded before the security runner reads.

This pattern is mechanical and uses only existing pytest extensibility. No new toolkit machinery, no new state stores beyond the session dict.

---

## 5. Acceptance YAML and security YAML — schemas unchanged

The substrate adds zero new fields to acceptance YAML or `feature.yaml::security.abuse_cases[]`. Existing schemas already carry everything needed. The walker reads them as-is.

### 5.1 WMBT acceptance (existing schema)

```yaml
urn: "wmbt:govern-lifecycle:D010"
acceptances:
  - identity:
      urn: "acc:govern-lifecycle:D010-UNIT-001-single-source-theme-map-helper"
      id: "AC-UNIT-001"
      purpose: "A single get_theme_map(config) helper replaces every hardcoded theme_map dict in the codebase"
      phase: "GREEN"
    harness:
      type: "unit"
      category: "backend"
    given:
      abstract:
        - "coach/utils/theme_map.py exposes get_theme_map(config) returning merged defaults + overrides"
        - "All prior hardcoded theme_map dicts have been replaced with calls to the helper"
    when:
      abstract: "A grep for hardcoded theme_map dict literals runs across src/atdd"
    then:
      abstract:
        - "No theme_map dict literal appears outside coach/utils/theme_map.py"
        - "inventory.py, registry.py, and test_train_validation.py import and call get_theme_map"
        - "The helper is the single source of truth for the digit-to-theme mapping"
    signal:
      metric: "hardcoded_theme_map_literal_count"
      threshold: 0
    metadata:
      author: "atdd:self-compliance"
      created: "2026-04-17"
```

Derived rule-ID: `repo.govern-lifecycle.D010-acc-unit-001`.

### 5.2 Train acceptance (existing schema)

```yaml
urn: "train:checkout-train"
acceptances:
  - identity:
      urn: "acc:checkout-train:idempotent-on-retry"
      id: "AC-SMOKE-001"
      purpose: "Re-running the flow with the same idempotency key produces no duplicate side effects"
      phase: "SMOKE"
    harness:
      type: "e2e"
    given: ...
    when: ...
    then: ...
    signal:
      metric: "duplicate_side_effects_on_retry"
      threshold: 0
```

Derived rule-ID: `repo.checkout-train.acc-idempotent-on-retry`.

### 5.3 Enforcement modes (implicit from existing fields)

The substrate doesn't introduce an `enforcement.type` discriminator. The discriminator is implicit:

- `harness.type` present → harness-mode (run the anchored test, expect assertion success).
- `signal.metric` + `signal.threshold` present → metric-mode (compute the metric, compare to threshold).
- Both present → both modes run, each through its own validator function (§4.2).

**Both-mode pass semantics.** Each mode goes through `assert_disposition_satisfied` as an independent call: harness mode calls the gate with `validator_id=<harness-test-module>::<harness-test-function>` and that mode's violation list; metric mode calls the gate with `validator_id=<metric-runner-module>::<metric-runner-function>` and its own violation list. The two pools are evaluated separately. Because both modes share the same `rule_id` (derived from the same `acc:` URN) and share `disposition: strict`, either pool containing one or more violations causes the gate to append a failure block for that mode. "Both must pass" formalizes as: each independent gate call must produce zero unsuppressed violations. Either mode failing alone blocks the phase. Strictness means suppression markers don't apply.

The `signal.metric` and `signal.threshold` fields are required together. An acceptance with one but not the other fails the measurability invariant.

### 5.4 Security artifacts (existing schema, see security convention §threat_modeling)

```yaml
# in plan/<wagon>/features/<feature>.yaml
urn: "feature:auth:session-management"
security:
  abuse_cases:
    - urn: "security:auth:session-management:001"
      id: "THREAT-001"
      name: "Session Hijacking"
      threat: "Attacker steals session token via XSS"
      mitigation: "HttpOnly cookies, CSP headers"
      severity: high
      acceptance_ref: "acc:auth:D001-SEC-001-session-protection"
```

Derived rule-ID: `repo.auth.session-management-security-001`.

The `urn:` field is added by the toolkit's `SecurityResolver` (see §10.0); current `feature.yaml` files have no abuse_cases authored yet. When the team starts authoring them, the URN is the canonical identifier.

---

## 6. Failure output

Repo-rule failures flow through `disposition_gate.py::_format_failure_block`. The format surfaces `description:` and `fix_hint:` from `RuleMetadata` above each violation block.

For acceptance-derived rules, `description` and `fix_hint` are composed from existing acceptance fields (see §4.2). The formatter is unchanged.

WMBT-acceptance rule, harness mode:

```
  rule_id=repo.govern-lifecycle.D010-acc-unit-001 disposition=strict validator=test_theme_map::test_no_hardcoded_literals (1 unsuppressed):
    description: A single get_theme_map(config) helper replaces every hardcoded theme_map dict in the codebase
    fix_hint:    No theme_map dict literal appears outside coach/utils/theme_map.py; inventory.py, registry.py, and test_train_validation.py import and call get_theme_map; The helper is the single source of truth for the digit-to-theme mapping
    [repo.govern-lifecycle.D010-acc-unit-001 sev=4] src/atdd/coach/commands/inventory.py:42: hardcoded theme_map dict literal found
```

WMBT-acceptance rule, metric mode (independent violation alongside or instead of harness):

```
  rule_id=repo.govern-lifecycle.D010-acc-unit-001 disposition=strict validator=test_metric_runner::test_metric_threshold_satisfied (1 unsuppressed):
    description: A single get_theme_map(config) helper replaces every hardcoded theme_map dict in the codebase
    fix_hint:    No theme_map dict literal appears outside coach/utils/theme_map.py; inventory.py, registry.py, and test_train_validation.py import and call get_theme_map; The helper is the single source of truth for the digit-to-theme mapping
    [repo.govern-lifecycle.D010-acc-unit-001 sev=4] codebase: hardcoded_theme_map_literal_count=3, threshold=0
```

Train-acceptance rule (SMOKE/E2E):

```
  rule_id=repo.checkout-train.acc-idempotent-on-retry disposition=strict validator=test_checkout_smoke::test_retry_is_idempotent (1 unsuppressed):
    description: Re-running the flow with the same idempotency key produces no duplicate side effects
    fix_hint:    The flow's final state is observably equivalent to a single invocation; no duplicate charges, emails, or inventory holds; idempotency is enforced at the flow boundary, not at any single step
    [repo.checkout-train.acc-idempotent-on-retry sev=4] tests/smoke/test_checkout.py:test_retry_is_idempotent: Second run produced a duplicate charge
```

Security rule (reference-binding mode):

```
  rule_id=repo.auth.session-management-security-001 disposition=strict validator=test_security_ref_binding::test_acceptance_ref_resolves_and_passes (1 unsuppressed):
    description: Session Hijacking — Attacker steals session token via XSS
    fix_hint:    HttpOnly cookies, CSP headers
    [repo.auth.session-management-security-001 sev=4] feature:auth:session-management: declared threat THREAT-001 has no resolved acceptance test (acceptance_ref points at acc:auth:D001-SEC-001-session-protection which does not exist in the graph)
```

The substrate is purely additive at the formatter level. It populates `RuleMetadata` from existing YAML; the formatter does what it already does.

---

## 7. Test anchoring and substrate enforcement

### 7.1 Existing header conventions

The toolkit's `TestResolver` already parses test files for header comments. The substrate uses these conventions verbatim:

```python
# URN: test:govern-lifecycle:D010-acc-unit-001
# Acceptance: acc:govern-lifecycle:D010-UNIT-001-single-source-theme-map-helper
# WMBT: wmbt:govern-lifecycle:D010
# Phase: GREEN
# Layer: domain

def test_no_hardcoded_literals():
    ...
```

For train-anchored tests, `# Train: train:<id>` replaces `# WMBT: ...`. These conventions are existing toolkit behavior, already enforced by `atdd repo validate`.

### 7.2 Runner pytest plugin

The substrate ships a pytest plugin (registered automatically by `atdd init`) that:

1. **At collection time**: for every test module under the repo's test root, reads the existing headers.
2. **For each anchored test function**: resolves the acceptance URN through `AcceptanceResolver`, derives the rule-ID per §3.3, calls `bind_rule()` to fetch the rule's metadata.
3. **At test-execution time**: wraps the test in an interception hook. On `AssertionError`, the hook constructs a `Violation` from the failure (rule_id, severity from registry, location from frame, detail from assertion message) and routes through `assert_disposition_satisfied()`.

Multiple tests may anchor to the same acceptance — the toolkit's `TESTED_BY` graph edge is one-to-many. The plugin processes each anchored test independently; each failing test produces its own gate call and failure block. The acceptance's rule passes iff every anchored test passes (§4.5).

Metric-mode enforcement runs in parallel through the metric runner (§4.5). When an acceptance has both modes, both runners produce violations independently, sequenced via the same pytest hooks that order the security runner.

The test author writes a normal-looking test. The runner does the rule-bound emission.

### 7.3 Substrate enforcement convention (toolkit-shipped)

The substrate's enforcement convention ships at `src/atdd/tester/conventions/acceptance-violation.convention.yaml`. These are toolkit conventions (toolkit rules), so their fix_hints are prescriptive — telling the team exactly what to add to make the rule pass.

```yaml
schema_version: "1.0.0"
convention_id: "tester.acceptance-violation"
name: "Acceptance Substrate Conformance"

rules:
  - id: tester.acceptance-violation.acceptance-must-be-measurable
    severity: 4
    disposition: strict
    validator: "test_acceptance_measurable::test_every_acceptance_has_enforcement"
    description: "Every acceptance in plan/ must declare harness.type with a binding test, OR signal.metric + signal.threshold (both fields required together), or both"
    fix_hint: |
      Under the failing acceptance, ensure at least one is present:
        - harness.type: <unit|backend|e2e|...> with a test file anchored to this acceptance via headers
        - signal.metric: <name> with signal.threshold: <value>
      If using signal mode, both fields are required — neither alone satisfies measurability.
    recipe: acceptance-measurability

  - id: tester.acceptance-violation.acceptance-must-declare-phase
    severity: 4
    disposition: strict
    validator: "test_acceptance_phase::test_every_acceptance_declares_phase"
    description: "Every acceptance in plan/ must declare identity.phase explicitly"
    fix_hint: |
      Under the failing acceptance's identity: block, add:
        phase: <RED|GREEN|SMOKE|REFACTOR>
      Phase is canonical for coach dispatch (§8.1) and cannot be inferred from source kind.
    recipe: acceptance-phase

  - id: tester.acceptance-violation.disposition-must-not-be-declared
    severity: 3
    disposition: strict
    validator: "test_acceptance_disposition::test_no_disposition_in_repo_yaml"
    description: "Repo acceptance and security YAML must NOT declare a disposition: field — the substrate sets it to strict for all repo rules"
    fix_hint: |
      Remove the disposition: field from the failing acceptance or abuse_case rule block.
      Repo contract rules are unsuppressible by construction (§2); declaring disposition is misleading.
    recipe: acceptance-rule-block

  - id: tester.acceptance-violation.validator-binding-must-be-bidirectional
    severity: 3
    disposition: strict
    validator: "test_repo_validator_binding::test_validator_binding_is_bidirectional"
    description: "When harness.type is declared, an anchored test must exist whose headers match the acceptance"
    fix_hint: |
      Either add the standard test header block at the top of the test file:
        # URN: test:<wagon-or-train>:<acceptance-slug>
        # Acceptance: <acc:URN>
        # WMBT: <wmbt:URN>      (or  # Train: <train:URN>)
        # Phase: <RED|GREEN|SMOKE|REFACTOR>
        # Layer: <presentation|application|domain|integration|assembly>
      Or fix the test to anchor at the right acceptance.
    recipe: acceptance-test-headers

  - id: tester.acceptance-violation.metric-implementation-must-exist
    severity: 4
    disposition: strict
    validator: "test_metric_implementation::test_every_signal_metric_has_compute_function"
    description: "When signal.metric is declared, a compute() implementation must exist in either <repo>/.atdd/metrics/<metric>.py or src/atdd/runners/metrics/<metric>.py (two-root lookup, repo-local takes precedence)"
    fix_hint: |
      The acceptance declares signal.metric: <name>, but no compute function exists in either lookup root:
        - <repo>/.atdd/metrics/<name>.py::compute       (repo-local; consumer-authored)
        - src/atdd/runners/metrics/<name>.py::compute   (toolkit-shipped; commons)
      Either add the missing implementation in <repo>/.atdd/metrics/<name>.py (no toolkit code change required),
      rename the metric to match an existing implementation, or remove signal.metric from the acceptance
      and rely on harness mode. The module must export compute(repo_root: Path) -> int|float|bool and
      passes(value, threshold) -> bool (default `value <= threshold` for upper-bound metrics).
    recipe: metric-implementation

  - id: tester.acceptance-violation.security-rule-must-have-acceptance-ref-resolved
    severity: 4
    disposition: strict
    validator: "test_security_ref_binding::test_every_abuse_case_resolves"
    description: "Every abuse_case in feature.yaml::security.abuse_cases[] must have acceptance_ref pointing at a real acceptance whose rule passes"
    fix_hint: |
      In the failing feature.yaml under security.abuse_cases[], the listed abuse_case has
      acceptance_ref: <acc:URN> that does not resolve to an acceptance in plan/. Either:
        - Author the missing acceptance (and its test) in the appropriate WMBT
        - Update acceptance_ref to point at an existing acceptance covering this threat
        - Remove the abuse_case if the threat is no longer in scope
    recipe: security-acceptance-binding
```

Recipes ship in the same toolkit directory:

- `src/atdd/tester/conventions/acceptance-measurability.recipe.yaml`
- `src/atdd/tester/conventions/acceptance-phase.recipe.yaml`
- `src/atdd/tester/conventions/acceptance-rule-block.recipe.yaml`
- `src/atdd/tester/conventions/acceptance-test-headers.recipe.yaml`
- `src/atdd/tester/conventions/metric-implementation.recipe.yaml`
- `src/atdd/tester/conventions/security-acceptance-binding.recipe.yaml`

Note: `test-must-be-anchored` is NOT a substrate enforcement rule. Header presence is already enforced by the existing `atdd repo validate` via `TestResolver`. The substrate doesn't duplicate.

### 7.4 Security rule enforcement (reference-binding)

Security rules don't have a test of their own. They enforce by reference: the rule passes iff `bound_acceptance_urn` resolves to a real acceptance AND that acceptance's rule passes.

Three failure modes, caught in two different places:

| Failure mode | Caught by | When |
|---|---|---|
| `bound_acceptance_urn` doesn't resolve | Substrate enforcement rule `security-rule-must-have-acceptance-ref-resolved` (§7.3) | Validation-time (PLANNED phase, or any `atdd repo validate` invocation) |
| `bound_acceptance_urn` resolves but the acceptance's rule failed in this run | Security-mode runner (§4.5) | Runtime (during the same pytest run as the acceptance, sequenced via pytest hooks) |
| `bound_acceptance_urn` resolves and the acceptance's rule passes | (no failure) | — |

The two-place split matters. The substrate enforcement rule fires at PLANNED phase whenever `atdd repo validate` runs — it surfaces missing references early, before the agent invests in implementation. The runtime runner fires at the phase the bound acceptance gates (RED/GREEN/SMOKE/REFACTOR) — it propagates failure when the threat's mitigation is in place but currently broken.

Security rules registered in `RuleMetadata` (i.e., resolution succeeded at registry-build time) carry a populated `bound_acceptance_urn`. Rules whose URN is unresolvable are not registered as security rules — they fire the enforcement rule at validation-time and stop there.

---

## 8. Coach integration

### 8.1 Tier-1 dispatch per phase

Coach v6 §6.5 selects validators per phase. With the substrate, dispatch is driven by each rule's `identity.phase` (set on the acceptance YAML, propagated to `RuleMetadata.phase` per §4.2), not by source kind. Source kind informs which rules coach considers (WMBT acceptances, train acceptances, security rules); `identity.phase` decides which considered rules apply at the current coach phase.

For each coach phase, the validator set is:

- Toolkit validators for that phase (planner / tester / coder / coder, respectively) — existing behavior.
- All repo rules whose `RuleMetadata.phase` matches the current coach phase, regardless of source kind.

So a coach phase running `GREEN` selects every repo rule with `phase: GREEN` — typically WMBT acceptances at GREEN, but also any train acceptance authored as `phase: GREEN` (rare but possible), or any security rule whose `bound_acceptance_urn` resolves to an acceptance at GREEN.

Security rules activate at whichever phase their bound acceptance activates; the coach reads `phase` on the bound acceptance's rule, not on the security rule itself.

The `REFACTOR` phase additionally sweeps every strict-disposition rule from both registries regardless of phase, as a regression check before COMPLETE.

**RED phase semantics — applies uniformly across all three runners.** An acceptance authored with `identity.phase: GREEN` declares that the contract should pass at GREEN. At RED, by ATDD convention, the same acceptance should *fail* (proving the contract exercises behavior not yet implemented). The substrate emits `Violation` records based on outcome regardless of phase, and this applies uniformly across the three runners:

- **Harness mode**: anchored tests fail at RED with `AssertionError`; the runner emits violations.
- **Metric mode**: the metric's `passes()` returns False at RED (e.g., `hardcoded_theme_map_literal_count > 0` because the helper hasn't been written yet); the runner emits violations.
- **Security mode**: the bound acceptance's rule failed at RED; the security runner emits a violation by reference.

In all three cases the disposition gate marks them as failures and the substrate surfaces them. The "RED expects red" semantics are coach's concern: coach v6 (§4.1) interprets violations at RED as expected and at GREEN as not. The substrate doesn't model this distinction; it surfaces violations and lets coach interpret per phase.

### 8.2 Spawn-harness `wmbt_rules` / `train_rules` / `security_rules` blocks

Coach v6 §7.1 includes a `conventions[].rules_in_scope` block in spawn prompts. The substrate adds three parallel blocks for repo-derived rules:

```yaml
conventions:
  - path: src/atdd/coder/conventions/dead-code.convention.yaml
    rules_in_scope: [...]
  - path: src/atdd/tester/conventions/acceptance-violation.convention.yaml
    rules_in_scope: [...]

wmbt_rules:                            # rules whose identity.phase matches current coach phase
  - wmbt_urn: wmbt:govern-lifecycle:D010
    rules:
      - id: repo.govern-lifecycle.D010-acc-unit-001
        acceptance_urn: acc:govern-lifecycle:D010-UNIT-001-single-source-theme-map-helper
        purpose: "A single get_theme_map(config) helper replaces every hardcoded theme_map dict in the codebase"
        expectations:
          - "No theme_map dict literal appears outside coach/utils/theme_map.py"
          - "inventory.py, registry.py, and test_train_validation.py import and call get_theme_map"
          - "The helper is the single source of truth for the digit-to-theme mapping"

train_rules:                           # rules whose identity.phase matches current coach phase
  - train_urn: train:checkout-train
    rules:
      - id: repo.checkout-train.acc-idempotent-on-retry
        purpose: "Re-running the flow with the same idempotency key produces no duplicate side effects"
        expectations: [...]

security_rules:                        # rules whose bound acceptance's identity.phase matches current coach phase
  - feature_urn: feature:auth:session-management
    rules:
      - id: repo.auth.session-management-security-001
        security_urn: security:auth:session-management:001
        threat: "Session Hijacking — Attacker steals session token via XSS"
        mitigation: "HttpOnly cookies, CSP headers"
        severity: 4
        acceptance_ref: acc:auth:D001-SEC-001-session-protection
```

Coach selects which blocks to include based on phase (per `identity.phase`) and diff scope.

### 8.3 Risk score archetype breakdown

Coach v6 §6.8 sums severity over active violations. The breakdown by archetype now has a `repo:` slice that lets the team see at a glance whether a PR's debt is in toolkit conventions or repo acceptances/security.

### 8.4 Train scope detection at SMOKE

When entering SMOKE phase, coach computes the in-scope train set:

1. From the diff, identify modified WMBTs (any WMBT YAML touched, or any test/code anchored to a touched WMBT).
2. For each modified WMBT, find its parent wagon (the directory under `plan/`).
3. For each touched wagon, query `_trains.yaml` for every train whose flow path includes that wagon.
4. Union the results.

Trains with no touched wagons skip — no SMOKE work for them. Wagon-touch detection reuses graph queries from `atdd repo`.

### 8.5 Suppression markers — ineffective for repo contract rules

Repo contract rules (acceptance-derived and security-derived) are unsuppressible by construction (see §2). The toolkit's `assert_disposition_satisfied` gate appends failures unconditionally for `disposition: strict`, without consulting the suppression scanner. Adding `# atdd:suppress(repo.<rule_id>) [UNTIL=<date>]` to a file does not silence the failure. A failing acceptance must be addressed by fixing the contract violation, deleting the acceptance, or editing the YAML to relax the contract — never by suppression.

This is intentional. Acceptance contracts are the line between done and not-done; allowing temporary silencing would erode the meaning of "GREEN passes." The toolkit's existing `suppress-and-clean` disposition is for cross-cutting toolkit conventions where migration debt is legitimately tracked; it is not a repo-rule mechanism.

When a WMBT/train/feature file is deleted, its derived rule-IDs leave the registry. Existing markers referencing those IDs (placed by mistake or as orphan debt) become unknown-rule and surface via the existing `test_rule_id_registry_coherence` validator.

### 8.6 No issue-close hook

Coach does nothing special on issue close. Plan files stay where they are; their rules keep enforcing.

---

## 9. CLI surface

### 9.1 `atdd urn` → `atdd repo` (hard rename)

The existing `atdd urn` command is renamed to `atdd repo`. Subcommands stay the same:

| Old | New |
|---|---|
| `atdd urn graph` | `atdd repo graph` |
| `atdd urn validate` | `atdd repo validate` |
| `atdd urn orphans` | `atdd repo orphans` |
| `atdd urn broken` | `atdd repo broken` |

Three new subcommands ship with the substrate:

```bash
atdd repo rules
  # For every acc:/security: URN in the graph, prints the derived rule-ID, the
  # parent URN, and whether the rule's enforcement is wired correctly.

atdd repo wmbt-rules <wmbt-urn>
  # Lists every derived rule for a specific WMBT.

atdd repo train-rules <train-urn>
  # Lists every derived rule for a specific train.

atdd repo security-rules <feature-urn>
  # Lists every derived security rule for a specific feature.
```

Migration of existing references (CI scripts, agent recipes, documentation, system prompts) happens as part of issue #8.

### 9.2 `atdd rules` extends transparently

`atdd rules show <id>`, `where <id>`, `grep <pattern>` work over `bind_rule()` and automatically see repo rules once the registry walker is extended. No CLI changes.

### 9.3 `atdd init` extension

`atdd init` is extended in consumer-repo mode to:

- Update `.atdd/config.yaml` with substrate fields (`repo.test_root`, etc.).
- Register the substrate's pytest plugin via the toolkit's existing pytest-plugin registration mechanism.

The toolkit detects mode by heuristic with explicit flag override:

- Default: presence of `plan/` AND absence of `src/atdd/` → consumer-repo mode (substrate active).
- `--consumer-repo` flag: force consumer-repo mode regardless of heuristic.
- `--toolkit` flag: force toolkit mode (no substrate registration; only existing toolkit init behavior).

The toolkit's own repo has both `plan/` (its dogfood acceptances) and `src/atdd/`. The default heuristic correctly identifies it as toolkit mode. When dogfooding the substrate against the toolkit's own plan/, run `atdd init --consumer-repo` to install the pytest plugin against the toolkit itself. Document this case in the toolkit CONTRIBUTING.md as part of issue #9.

---

## 10. Implementation plan

The implementation is split into **8 tracks** dispatched across **6 parallel agents** rather than sequential waves. Tracks are scoped by dependency boundary, not by spec section. The full set of 17 issues with their bodies is in `atdd-repo-substrate-issues.md` (companion document); this section references them by number.

### 10.0 Track summary

| Track | Owner | Scope | Issues | Depends on |
|---|---|---|---|---|
| A — Rule registry substrate | Agent 1 | `repo` archetype, `RuleMetadata` extension, registry walker, CLI discovery | #1, #2, #3 | — |
| B — Conformance validators | Agent 2 | Five substrate enforcement rules (§7.3) and recipes | #4 | A (#1, #2) |
| C — Harness-mode plugin | Agent 3 | Pytest plugin, header parsing, assertion interception, N-to-1 binding | #5 | A (#1, #2) |
| D — Metric runner | Agent 4 | Two-root metric-function discovery, runner, dogfood metric | #6, #7 | A (#1) |
| E — CLI / init | Agent 5 | `atdd urn` → `atdd repo` rename, `atdd init` extension | #8, #9 | A (#2), C (#5) |
| F — Coach integration | (merge-window) | Phase dispatch, spawn-harness blocks, risk-score breakdown | #10, #11, #12 | A, C, D, E |
| G — Security Workstream A | Agent 6 | `SecurityResolver`, URN grammar, graph edges, audit | #13, #14, #15 | — |
| H — Security substrate | Agent 6 | Security rule walker, runner, ordering, CLI | #16 | G, A, C, D |
| I — Integration acceptance | (merge) | End-to-end worked example | #17 | A through E |

Tracks A through E and G run in parallel. F is a merge-window task picked up after C/D/E land. H runs after G + A/C/D. I (#17) is the substrate's done-line and gates on the rest.

### 10.1 Sequencing within tracks

**Track A** is the foundation. Issues sequence as #1 → #2 → #3. Other tracks depend on at least #1 and most depend on #2 landing first.

**Track B** starts after A's #1 and #2 land. The validators consume `RuleMetadata` and walk the registry; both must be stable before B can implement against them rather than against fixtures. Agent 2 may write stubs during the wait but does not merge until A is stable.

**Track C** starts after #1 and #2. The pytest plugin reads the registry and dispatches per rule; same stability requirement as B.

**Track D** starts after #1. Issue #6 (metric runner) is independent of registry walker for the runner itself; #7 (the dogfood metric) depends on #6.

**Track E** starts after #2. The new `atdd repo rules` / `wmbt-rules` / `train-rules` subcommands need data to query, which #2 produces. The rename (#8) before the `atdd init` extension (#9) so init's docs reference current names.

**Track F** is a merge-window task, not a dedicated agent's track. Pick up after C, D, and E are green. Agent 1 or Agent 3 owns it during integration.

**Track G** runs fully in parallel with everything else. Workstream A is a coordinated toolkit upgrade; its three issues (#13, #14, #15) sequence among themselves but don't gate on substrate work.

**Track H** runs after G + A (#2) + C (#5) + D (#6). Issue #16 consolidates what was previously S3.1–S3.5 into one issue because the parts are tightly coupled (registry consumption, runner, ordering, CLI all share infrastructure).

**Track I** (#17) is the substrate's done-line. It validates that the substrate fires on a real WMBT and a real train end-to-end, with both Class 1 (conformance) and Class 2 (contract) failures producing the expected feedback shape. Until #17 passes, the substrate is not done — even if all upstream issues are individually closed.

### 10.2 Toolkit prerequisite (Workstream A — Track G)

Workstream A items consolidate into three issues per §10.1 Track G: #13 (resolver + registration + graph edges), #14 (URN grammar validator + convention update), #15 (hardcoding audit + report). The substrate spec's §3.2 (parent-it-belongs-to principle) is the convention update of #14.

The substrate spec depends on Workstream A delivering: security URNs of the documented form `security:<wagon>:<feature-slug>:<threat-seq>`, resolver returning abuse_case fields including `severity`, `acceptance_ref`, `name`, `threat`, `mitigation`; graph edges from features to security artifacts and from security artifacts to referenced acceptances; `atdd repo validate` reporting broken `acceptance_ref` and unresolved `security:` URNs.

### 10.3 PR review burden

Six agents producing 17 issues will produce roughly 17–25 PRs (some issues spawn follow-ups). Sustainable review load is roughly one human reviewer per 2–3 active agent PRs. If review bandwidth is constrained, scale down to 3–4 agents and accept slower wall-clock progress to avoid PR queue collapse.

### 10.4 Hard rename impact (Issue #8)

The `atdd urn` → `atdd repo` rename is a one-time downstream cost for any consumer-repo CI configs that reference `atdd urn`. CHANGELOG includes a sed migration command: `sed -i 's/atdd urn/atdd repo/g' <files>`. No backward-compat alias — hard rename per design decision.

---

## 11. Day-1 experience

A repo flipping the substrate on for the first time sees two distinct classes of failure, with different feedback shapes.

**Class 1 — Substrate conformance failures.** Surfaced by the substrate enforcement rules (§7.3, all under `tester.acceptance-violation.*`). These are toolkit-authored conventions, so each carries a prescriptive `recipe:` pointer telling the team exactly what to add or remove to make the rule pass. Categories:

- "These N acceptances fail measurability." `tester.acceptance-violation.acceptance-must-be-measurable` → `recipe:acceptance-measurability`.
- "These N acceptances are missing identity.phase." `tester.acceptance-violation.acceptance-must-declare-phase` → `recipe:acceptance-phase`.
- "These N YAMLs declare disposition (forbidden)." `tester.acceptance-violation.disposition-must-not-be-declared` → `recipe:acceptance-rule-block`.
- "These M validator bindings are inconsistent." `tester.acceptance-violation.validator-binding-must-be-bidirectional` → `recipe:acceptance-test-headers`.
- "These K signal.metric implementations are missing." `tester.acceptance-violation.metric-implementation-must-exist` → `recipe:metric-implementation`.
- (Once issues #13, #14, #16 land:) "These J abuse_cases have unresolved acceptance_ref." `tester.acceptance-violation.security-rule-must-have-acceptance-ref-resolved` → `recipe:security-acceptance-binding`.

The output may also include findings from existing `atdd repo validate` graph validators (orphan tests, broken URN references, structural issues). These pre-date the substrate; their findings are rule-IDed in the same shape and follow the same recipe-pointer workflow.

**Class 2 — Acceptance and security rule failures.** Surfaced by the runners (§4.5) when actual contracts fail. These are repo rules, not conventions, so they do NOT carry a recipe pointer (recipes are prescriptive; acceptance rules describe contracts not implementations — see §2). Each failure surfaces:

- `description` (composed from `identity.purpose` for acceptance rules, or `name` + `threat` for security rules)
- `fix_hint` (composed from `then.abstract` joined for acceptance rules, or `mitigation` for security rules)
- The structured `Violation` record with location and detail

The agent reads the contract and the expected behavior from these fields and works in the domain; there is no recipe to follow because how to satisfy the contract is the agent's modeling work.

**Workflow:**

1. **Run `atdd init`.** Updates config, registers pytest plugin.
2. **Run `atdd repo validate`.** Class 1 failures fire (substrate conformance + graph validators).
3. **Agent works through Class 1 failures.** Each carries a recipe pointer; the fix is mechanical.
4. **Re-run `atdd repo validate`.** Class 1 count drops to zero as fixes land.
5. **Run the test suite.** Class 2 failures (real contract violations) now surface — substrate is self-policing.
6. **Agent works through Class 2 failures.** Read the contract, model the domain, fix the implementation.

Strict from day 1. Class 1 is concentrated migration work; Class 2 is ongoing development feedback.

---

## 12. Out of scope (and explicit deferrals)

- Auto-generation of acceptance tests from acceptance YAML.
- Cross-repo rule sharing.
- IDE integration (rule-ID linting in editors).
- Auto-cleanup of orphaned suppression markers when WMBTs/trains/features are deleted (manual).
- Multi-language test-runner adapters. The substrate ships a pytest plugin. Repos with Flutter/jest/vitest/go test acceptance suites need per-framework runner adapters following the same pattern.
- Toolkit existing security-convention `documentation-only` rules potentially flippable to `strict` once abuse cases become rules. This is a follow-up decision for the toolkit team, not part of this substrate spec.
- **Acceptance URN aliasing.** Renaming an `acc:` URN changes the derived rule-ID. The toolkit's convention rules support `aliases:` for stable IDs; repo rules do not. The URN graph already enforces URN stability via `atdd repo validate`; renaming surfaces as a graph break. If aliasing for repo rules becomes operationally needed, it can be added later as a non-breaking extension.
- **Pre-commit hook integration.** The substrate's pytest plugin runs only on pytest invocation, not on every pre-commit. CI catches substrate failures. A "substrate pre-commit fast-path" is deferred to a future enhancement if operationally painful.
- **Orphan tests after acceptance deletion.** Already caught by existing `atdd repo validate` graph validators. The substrate doesn't duplicate.
- **Pre-Workstream-A handling of `feature.yaml::security.abuse_cases[]`.** Until A lands, abuse_case blocks in `feature.yaml` are silently tolerated (the toolkit doesn't read them). Post-A, they're parsed; pre-A YAMLs become substrate rules at S3 landing, possibly producing day-1 failures retroactively. Document at S3 landing.

---

## 13. Glossary

- **Repo rule** — any rule whose archetype is `repo`. Sourced from WMBT acceptances, train acceptances, or security artifacts.
- **WMBT-acceptance rule** — repo rule derived from a WMBT acceptance. Drives RED/GREEN/REFACTOR.
- **Train-acceptance rule** — repo rule derived from a train acceptance. Drives SMOKE/E2E.
- **Security rule** — repo rule derived from a `feature.yaml::security.abuse_cases[]` entry. Enforces by reference-binding to a covering acceptance.
- **Derived rule-ID** — rule-ID computed mechanically from an `acc:` or `security:` URN per §3.3.
- **Test anchor** — header comments (`# URN: test:...`, `# Acceptance: ...`, `# WMBT: ...` or `# Train: ...`, `# Phase: ...`, `# Layer: ...`) that locate a test in the URN graph.
- **Runner** — toolkit-shipped functions that read rule metadata, dispatch enforcement, and route violations through `assert_disposition_satisfied()`. Three runners: harness-mode (pytest plugin, N anchored tests per rule), metric-mode (single computation per rule), security-mode (single resolution per rule). All N-to-1: rule passes iff every validation passes. See §4.5.
- **Metric-function registry** — two-root discovery mechanism mapping declared `signal.metric` names to their compute functions. Repo-local `<repo>/.atdd/metrics/<metric>.py::compute` (consumer-authored, wins on collision) takes precedence over toolkit-shipped `src/atdd/runners/metrics/<metric>.py::compute`. Each module exposes `compute()` and `passes()`. See §4.5.
- **Session result map** — pytest-session-scoped namespace `session._atdd["rule_outcomes"]` populated by `pytest_runtest_logreport` recording per-rule outcomes. Read by the security-mode runner (§4.5) which executes after acceptance runners via `pytest_collection_modifyitems` ordering.
- **Reference-binding enforcement** — security rule's mode: passes iff `bound_acceptance_urn` resolves and the referenced acceptance's rule passes.
- **Parent-it-belongs-to principle** — URN segment count reflects the parent's identification cost, not a fixed scheme depth (§3.2).
- **Workstream A** — toolkit prerequisite for substrate's security integration: `SecurityResolver`, registry registration, URN grammar validator, URN convention update, graph builder edges, hardcoding audit. See §10.2 (Track G, issues #13–#15).

---

## 14. Relationship to coach spec v6

This substrate spec is *additive* to coach v6. Coach does not change to support repo rules — it consumes them transparently through `bind_rule()` and the disposition gate. Integration points:

- Registry walker reads three new source classes (§4).
- Phase-validator selection extends with WMBT, train, and security rules (§8.1).
- Spawn-harness adds `wmbt_rules:`, `train_rules:`, `security_rules:` blocks (§8.2).
- Risk score breakdown surfaces a `repo:` slice (§8.3).
- Train-scope detection at SMOKE (§8.4).

All extensions of existing coach mechanisms.
