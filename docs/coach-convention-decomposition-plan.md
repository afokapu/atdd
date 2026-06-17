# Coach Convention Decomposition Plan

> **Slice 1 of umbrella #1113** — issue **#1114**. This is the classification gate.
> It authors **no convention nodes** and changes **no relationship graph**. Its
> only job is to classify every section of the 17 coach `*.convention.yaml` files
> so Slice 2 can atomize **only the core material** without freezing today's
> platform/runtime choices (GitHub, git-worktree, cmux, Claude, pytest) into the
> ATDD core protocol.

## How to read this

Each section of each coach convention is classified as one of:

| class | meaning | Slice-2 action |
|-------|---------|----------------|
| `core` | protocol-level; true without GitHub/git/cmux/Claude/pytest | author as a v1.1.0 node |
| `extension` | platform/tool behavior (GitHub, gh, PR) | move to an extension package (Slice 3) |
| `workspace` | runtime execution (git-worktree, cmux, Claude, pytest) | move to a workspace provider (Slice 3) |
| `legacy_redirect` | authority now lives elsewhere (e.g. planner nodes) | retire/redirect; do not re-author in coach |
| `design_candidate` | wanted by the aligned model but no stable legacy source | record as follow-up; do **not** author a node |

### Two shapes of `core`

1. **Protocol material** currently embedded in `coach`, `session`, `observer`,
   `issue`, `pr` → re-homed into the six aligned families
   `coach.{lifecycle,execution,extension,workspace,graph,role}.*`.
2. **Toolkit-self conventions** (`rule-id`, `source-layout`, `wheel-completeness`,
   `template`, the core slice of `code-roots`) keep their existing
   `coach.<convention>.<slug>` family and carry `metadata.core_surface: toolkit_self`
   + `metadata.not_generalized_to_workspace: true` (per #1113 Decision #4). These
   govern ATDD-the-tool's own integrity, not extension runtime — so they are core,
   but they are **not** the six protocol families.

### Row schema

Every row below carries the machine-actionable fields from #1113 so Slice 2's
no-leakage guard is a mechanical join (`every authored core node's
source.legacy_rule_id resolves to a row with classification: core`):

```
source_file, source_section, source_rule_id, classification,
target_package_kind, target_package_id, candidate_rule_id, reason, notes
```

`source_rule_id: null` where the section has no existing rule id (it's prose/data).
`candidate_rule_id` is filled only for `core` rows. Target package ids are
provisional names for Slice 3.

---

## Summary (17 files)

| File | Dominant class | Core rows | Headline |
|------|----------------|-----------|----------|
| `phase_machine.convention.yaml` | core | 1 | pure lifecycle state machine — the seed of `coach.lifecycle.*` |
| `rule-id.convention.yaml` | core (toolkit_self) | 5 | rule-ID system; 2 misfiled PR rules → extension |
| `source-layout.convention.yaml` | core (toolkit_self) | 2 | distribution invariant across source/editable/wheel |
| `wheel-completeness.convention.yaml` | core (toolkit_self) | 1 | shipped-fixture distribution invariant |
| `template.convention.yaml` | core | 1 | template must not duplicate canonical conventions |
| `code-roots.convention.yaml` | core (split) | 1 | config-driven root resolution; stack defaults → follow-up |
| `coach.convention.yaml` | mixed | 3 | core operating principles; cmux/Feed launch → workspace |
| `session.convention.yaml` | mixed | 3 | freedom-with-leash model core; bash/cmux/Claude → workspace |
| `observer.convention.yaml` | mixed | 4 | out-of-contract→correction/operator core; regexes/cmux → workspace |
| `issue.convention.yaml` | mixed | 5 | lifecycle/role-sequence core; GitHub tracking → extension; local-session model → legacy |
| `pr.convention.yaml` | extension | 2 | thin core (no-terminal-pre-SMOKE, runtime≠artifact); rest GitHub |
| `commit-trailers.convention.yaml` | workspace | 0 | git/issue trailer mechanics; provenance concept → design_candidate |
| `forbidden_commands.convention.yaml` | mixed | 1 | classifier substrate core; gh/cmux/git patterns → ext/ws |
| `path_shim_gh.convention.yaml` | extension | 0 | gh-issue-create shim → github extension |
| `path_shim_git.convention.yaml` | workspace | 0 | git-config-bare shim → git-worktree workspace |
| `spawn.convention.yaml` | workspace | 0 | cmux+Claude launch entry point |
| `naming.convention.yaml` | legacy_redirect | 1 | per-archetype patterns → planner/tester nodes; appendix/system retained |

**Totals (50 machine-actionable rows; a row may bundle related sub-rules):**
core **28**, workspace **8**, extension **7**, legacy_redirect **4**,
design_candidate **3**. The "Core rows" column above counts distinct core *concepts*
per file (some bundled into one row). Counts firm up if Slice-1 review re-cuts any
mixed section.

---

## Machine-actionable rows

```yaml
rows:
  # ── phase_machine.convention.yaml ──────────────────────────────────────────
  - source_file: phase_machine.convention.yaml
    source_section: phases
    source_rule_id: coach.phase-machine
    classification: core
    target_package_kind: core
    target_package_id: core
    candidate_rule_id: coach.lifecycle.phase-machine
    reason: Pure ATDD lifecycle state machine (phase -> agent/transitions_to/pre_commit_gate); no platform.
    notes: The seed for coach.lifecycle.*. May split into phase-ordering + phase-entry/exit + terminal-state-discipline in Slice 2; pre_commit_gate command string is core but its validator target is archetype-specific.

  # ── rule-id.convention.yaml (toolkit_self) ─────────────────────────────────
  - source_file: rule-id.convention.yaml
    source_section: "grammar + legacy_grammar + domains + severity_scale + rule_schema"
    source_rule_id: null
    classification: core
    target_package_kind: core
    target_package_id: core
    candidate_rule_id: coach.rule-id.grammar-and-schema
    reason: The rule-ID system itself — grammar, domain registry, severity scale, per-rule YAML shape. Governs the nodes we author.
    notes: "core_surface: toolkit_self. This is the meta-convention for convention nodes; keep coach.rule-id.* family. May become several nodes."
  - source_file: rule-id.convention.yaml
    source_section: "rule_schema.fields.fix_hint.completeness_contract + fix_hint_exemplars"
    source_rule_id: coach.rule-id.fix-hint-completeness
    classification: core
    target_package_kind: core
    target_package_id: core
    candidate_rule_id: coach.rule-id.fix-hint-completeness
    reason: C1-C4 fix-hint completeness contract; protocol quality bar for rules.
    notes: "core_surface: toolkit_self."
  - source_file: rule-id.convention.yaml
    source_section: "rules[coach.rule-id.*]"
    source_rule_id: "coach.rule-id.no-hardcoded-rule-severity; coach.rule-id.disposition-required; coach.rule-id.stale-suppression; coach.rule-id.validator-binding-violation"
    classification: core
    target_package_kind: core
    target_package_id: core
    candidate_rule_id: coach.rule-id.<slug>
    reason: Disposition model, suppression discipline, bidirectional binding contract — the rule system's own invariants.
    notes: "core_surface: toolkit_self. 4 rules; keep ids verbatim."
  - source_file: rule-id.convention.yaml
    source_section: migration
    source_rule_id: null
    classification: core
    target_package_kind: core
    target_package_id: core
    candidate_rule_id: coach.rule-id.migration-playbook
    reason: Retrofit playbook + disposition_compatibility + deprecation window for migrating conventions to structured rules.
    notes: "core_surface: toolkit_self. The `completed:` list is data, not normative — may stay in legacy file."
  - source_file: rule-id.convention.yaml
    source_section: "rules[coach.initializer.template-cli-drift; coach.workflow-template.command-must-parse]"
    source_rule_id: "coach.initializer.template-cli-drift; coach.workflow-template.command-must-parse"
    classification: core
    target_package_kind: core
    target_package_id: core
    candidate_rule_id: coach.workspace.emitted-cli-must-parse
    reason: Guards that the toolkit's own emitted `atdd ...` workflow lines parse under the live CLI — ATDD-tool integrity.
    notes: "core_surface: toolkit_self. Emits into consumer .github workflow templates; the workflow YAML target is github but the invariant is CLI-self-consistency."
  - source_file: rule-id.convention.yaml
    source_section: "rules[coach.pr.base-must-be-default-branch; coach.pr.mass-delete-guard]"
    source_rule_id: "coach.pr.base-must-be-default-branch; coach.pr.mass-delete-guard"
    classification: extension
    target_package_kind: extension
    target_package_id: atdd.extension.github
    candidate_rule_id: null
    reason: Misfiled GitHub PR rules (PR base branch, mass-delete guard) — platform behavior, not the rule-ID system.
    notes: Co-locate with pr.convention rules in the github extension. Sibling pointer already noted in pr.convention.references.

  # ── source-layout.convention.yaml (toolkit_self) ───────────────────────────
  - source_file: source-layout.convention.yaml
    source_section: "rules[coach.source-layout.no-toolkit-self-layout-assumption]"
    source_rule_id: coach.source-layout.no-toolkit-self-layout-assumption
    classification: core
    target_package_kind: core
    target_package_id: core
    candidate_rule_id: coach.source-layout.no-toolkit-self-layout-assumption
    reason: ATDD code must resolve its own package resources package-relatively, valid across source/editable/wheel.
    notes: "core_surface: toolkit_self, not_generalized_to_workspace: true. Mentions Python but the invariant is ATDD distribution integrity."
  - source_file: source-layout.convention.yaml
    source_section: "rules[coach.source-layout.no-bare-version-detection]"
    source_rule_id: coach.source-layout.no-bare-version-detection
    classification: core
    target_package_kind: core
    target_package_id: core
    candidate_rule_id: coach.source-layout.no-bare-version-detection
    reason: version("atdd") only inside the canonical try/except — ATDD must run from source without a wheel.
    notes: "core_surface: toolkit_self."

  # ── wheel-completeness.convention.yaml (toolkit_self) ──────────────────────
  - source_file: wheel-completeness.convention.yaml
    source_section: "rules[coach.wheel-completeness.fixture-missing-from-wheel]"
    source_rule_id: coach.wheel-completeness.fixture-missing-from-wheel
    classification: core
    target_package_kind: core
    target_package_id: core
    candidate_rule_id: coach.wheel-completeness.fixture-missing-from-wheel
    reason: Shipped validators' fixtures must be present in the installed ATDD package — release-artifact integrity.
    notes: "core_surface: toolkit_self. Python wheel is the current distribution mechanism, not a protocol-wide claim."

  # ── template.convention.yaml ───────────────────────────────────────────────
  - source_file: template.convention.yaml
    source_section: "rules[coach.template.no-duplicated-convention]"
    source_rule_id: coach.template.no-duplicated-convention
    classification: core
    target_package_kind: core
    target_package_id: core
    candidate_rule_id: coach.template.no-duplicated-convention
    reason: The agent-facing template must point at canonical sources, not duplicate them — protocol invariant on authority.
    notes: Genuinely coach-owned (NOT legacy_redirect). The forbidden-section list references canonical homes; keep the rule, the list is data.

  # ── code-roots.convention.yaml (split) ─────────────────────────────────────
  - source_file: code-roots.convention.yaml
    source_section: "config_surface + resolver_contract(skip_unknown, signature, root-as-arg) + how_to_add_a_stack"
    source_rule_id: null
    classification: core
    target_package_kind: core
    target_package_id: core
    candidate_rule_id: coach.graph.implementation-root-resolution
    reason: Implementation-root discovery must be config-driven (not hardcoded), accept root as an arg, and not crash on unknown stacks.
    notes: Resolution/binding, not live invocation (so coach.graph.*, not coach.execution.*). Statement per #1113.
  - source_file: code-roots.convention.yaml
    source_section: "config_surface.defaults + toolkit_heuristic + _RESOLVERS registry + baseline_policy"
    source_rule_id: null
    classification: workspace
    target_package_kind: workspace
    target_package_id: atdd.workspace.python-pytest
    candidate_rule_id: null
    reason: python/supabase/web default roots, the toolkit fuzzy-match heuristic, and the concrete resolver registry are stack-specific.
    notes: Slice 2 must NOT overbuild the split — keep the core invariant only; file follow-ups for stack resolver ownership. baseline_policy is toolkit_self bookkeeping.

  # ── coach.convention.yaml ──────────────────────────────────────────────────
  - source_file: coach.convention.yaml
    source_section: "core_principle + rules[coach.activation.one-agent-per-session-unit]"
    source_rule_id: coach.activation.one-agent-per-session-unit
    classification: core
    target_package_kind: core
    target_package_id: core
    candidate_rule_id: coach.execution.one-agent-per-delivery-unit
    reason: One delivery unit -> one isolated execution context -> one agent; no shared context / sub-agent delegation. Protocol abstraction over worktree+cmux.
    notes: Abstract the concrete "git worktree + cmux workspace" to "isolated execution context". wave_planning/two_phase_commit pointers are implementation, not normative.
  - source_file: coach.convention.yaml
    source_section: "feed_mediation (decisions surface for mediation) + rules[coach.activation.decisions-surface-to-feed]"
    source_rule_id: coach.activation.decisions-surface-to-feed
    classification: core
    target_package_kind: core
    target_package_id: core
    candidate_rule_id: coach.execution.decisions-mediated-not-auto-executed
    reason: Worker decisions (dangerous/ambiguous) must surface for mediation rather than auto-execute. Protocol concept.
    notes: The cmux Feed + `cmux feed.question.reply` transport is workspace (see workspace row). Keep the mediation requirement core.
  - source_file: coach.convention.yaml
    source_section: feed_mediation.dangerous_permission_policy
    source_rule_id: null
    classification: core
    target_package_kind: core
    target_package_id: core
    candidate_rule_id: coach.role.operator-decision-authority
    reason: Dangerous (deny-pattern) decisions default to ESCALATE to the operator; a dangerous decision requires operator policy.
    notes: Maps escalation -> lifecycle/role operator-required. DaemonConfig field is implementation.
  - source_file: coach.convention.yaml
    source_section: "activation + launch_transport + observer_corrections (transport) + rules[coach.activation.cmux-native-launch]"
    source_rule_id: coach.activation.cmux-native-launch
    classification: workspace
    target_package_kind: workspace
    target_package_id: atdd.workspace.cmux-claude
    candidate_rule_id: null
    reason: cmux-native launch (claude positional prompt), cmux Feed transport, cli-return.jsonl correction inbox — concrete runtime transport.
    notes: The `atdd coach` activation CLI surface is toolkit; the cmux/Claude launch mechanics are the workspace. observer_corrections concept is core (see observer rows), transport is workspace.

  # ── session.convention.yaml ────────────────────────────────────────────────
  - source_file: session.convention.yaml
    source_section: "spawn_time.freedom_layer.invariant (freedom-with-a-leash; destructive must surface)"
    source_rule_id: null
    classification: core
    target_package_kind: core
    target_package_id: core
    candidate_rule_id: coach.execution.freedom-with-a-leash
    reason: Two-layer model — safe set runs unattended; destructive/outward actions must surface, never auto-execute. Protocol-level.
    notes: The concrete allowed_tools/allowed_bash/forbidden_bash tables are stack-specific data -> workspace row below.
  - source_file: session.convention.yaml
    source_section: "spawn_time.deny_pattern_escalation + spawn_time.leash_layer (correction concept)"
    source_rule_id: null
    classification: core
    target_package_kind: core
    target_package_id: core
    candidate_rule_id: coach.execution.structured-correction-and-escalation
    reason: Corrections use a structured channel; deny-pattern actions route to structured escalation, never modal typing. Protocol.
    notes: cli-return.jsonl and `atdd agent escalate` mechanisms are workspace; the structured-not-ad-hoc requirement is core.
  - source_file: session.convention.yaml
    source_section: "spawn_time.freedom_layer.{allowed_tools,allowed_bash,forbidden_bash} + slash_command_prohibition + session_naming + layout_placement + multiplexer + rules[coach.launch-prompt..., coach.session.*]"
    source_rule_id: "coach.session.canonical-session-name; coach.session.canonical-role-name; coach.session.layout-conformance; coach.launch-prompt.must-include-wagon-graph"
    classification: workspace
    target_package_kind: workspace
    target_package_id: atdd.workspace.cmux-claude
    candidate_rule_id: null
    reason: Concrete bash tables, Claude flags, cmux tab/surface naming + grid layout policy, multiplexer preference — runtime config.
    notes: Stack-specific (#1035 supplies non-Python tables). session_naming/layout are cmux drift rules. launch-prompt wagon-graph is a template/spawn concern -> workspace/extension.
  - source_file: session.convention.yaml
    source_section: "spawn_time.freedom_layer (config-as-data is the source of truth invariant, E031)"
    source_rule_id: null
    classification: design_candidate
    target_package_kind: none
    target_package_id: none
    candidate_rule_id: coach.workspace.freedom-set-declared-as-data
    reason: "The protocol-level half of E031 — the freedom set is DATA read by launch planes, not a code literal — could be a core workspace-contract rule."
    notes: Needs the workspace provider contract to exist first; record as follow-up, do not author now.

  # ── observer.convention.yaml ───────────────────────────────────────────────
  - source_file: observer.convention.yaml
    source_section: "basic_protocol_observer_rules[reviewer-edit-attempt]"
    source_rule_id: coach.observer.reviewer-edit-attempt
    classification: core
    target_package_kind: core
    target_package_id: core
    candidate_rule_id: coach.role.reviewer-no-write
    reason: Reviewer persona may not edit or commit — the reviewer no-write contract. Pure role semantics.
    notes: Detection (screen capture) is workspace; the contract is core role.
  - source_file: observer.convention.yaml
    source_section: "basic_protocol_observer_rules[out-of-scope-edit, completion-claim-without-commit, validator-failure-ignored]"
    source_rule_id: "coach.observer.out-of-scope-edit; coach.observer.completion-claim-without-commit; coach.observer.validator-failure-ignored"
    classification: core
    target_package_kind: core
    target_package_id: core
    candidate_rule_id: coach.execution.out-of-contract-detection
    reason: Out-of-contract behavior (scope creep, false completion, ignored violations) must be detected and corrected. Protocol concept.
    notes: These are documentation-only runtime advisories; abstract the concept, not the cmux detection plumbing.
  - source_file: observer.convention.yaml
    source_section: "drift_classifier_observer_rules[smoke-skip]"
    source_rule_id: coach.observer.smoke-skip
    classification: core
    target_package_kind: core
    target_package_id: core
    candidate_rule_id: coach.lifecycle.no-green-to-refactor-without-smoke
    reason: A GREEN->REFACTOR transition without an intervening SMOKE is a phase-ordering violation. Lifecycle invariant.
    notes: Reinforces phase_machine ordering; consider folding into coach.lifecycle.phase-ordering in Slice 2.
  - source_file: observer.convention.yaml
    source_section: "basic_protocol_observer_rules[unstructured-question, token-silence, missed-heartbeat]"
    source_rule_id: "coach.observer.unstructured-question; coach.observer.token-silence; coach.observer.missed-heartbeat"
    classification: core
    target_package_kind: core
    target_package_id: core
    candidate_rule_id: coach.execution.agent-liveness-and-structured-asks
    reason: Agents must use structured ask/escalate channels and remain live (heartbeat/no-silence). Protocol-level execution discipline.
    notes: Thresholds + `atdd agent ask/heartbeat` CLI are workspace mechanisms; the requirement is core.
  - source_file: observer.convention.yaml
    source_section: "token_threshold_observer_rule + bash_classifier(auto_approve_patterns, deny_patterns) + drift_classifier[bash-auto-approve, canonical-naming-drift, layout-drift]"
    source_rule_id: "coach.observer.token-threshold; coach.observer.bash-*; coach.observer.canonical-naming-drift; coach.observer.layout-drift"
    classification: workspace
    target_package_kind: workspace
    target_package_id: atdd.workspace.cmux-claude
    candidate_rule_id: null
    reason: Concrete bash regexes, token-count threshold tied to the agent runtime, cmux surface naming/layout drift correctors.
    notes: The deny-before-allow safety ordering is a reusable workspace-contract idea; the regex tables themselves are stack/runtime data.

  # ── issue.convention.yaml ──────────────────────────────────────────────────
  - source_file: issue.convention.yaml
    source_section: "workflow.enforcement.sequence_rules (WF-001..004) + workflow.principle + violation_handling"
    source_rule_id: "WF-001; WF-002; WF-003; WF-004"
    classification: core
    target_package_kind: core
    target_package_id: core
    candidate_rule_id: coach.role.planner-tester-coder-sequence
    reason: Plan-before-test, test-before-code, RED-before-implementation, GREEN-before-REFACTOR; skip -> BLOCKED. Core role sequencing + lifecycle.
    notes: The artifact paths/validators in workflow.phases are planner/tester/coder specifics -> legacy_redirect row below.
  - source_file: issue.convention.yaml
    source_section: workflow.session_type_workflows
    source_rule_id: null
    classification: core
    target_package_kind: core
    target_package_id: core
    candidate_rule_id: coach.lifecycle.session-type-required-phases
    reason: Each session/issue type declares its required phases (implementation=full cycle, analysis=none, planning=planner-only, ...). Lifecycle data.
    notes: Maps directly onto phase_machine; consider a single coach.lifecycle node referencing the type->phases table.
  - source_file: issue.convention.yaml
    source_section: status.auto_transition_on_merge (single-step advance per state machine)
    source_rule_id: null
    classification: core
    target_package_kind: core
    target_package_id: core
    candidate_rule_id: coach.lifecycle.single-step-advance-on-delivery
    reason: On a delivery event, advance exactly one step per the state machine; terminal/pre-impl phases are no-ops. Lifecycle transition policy.
    notes: The PR-merge trigger + .github workflow + `atdd auto-phase` are the github extension mechanism (row below). Keep the single-step-advance rule core.
  - source_file: issue.convention.yaml
    source_section: manifest_write_discipline
    source_rule_id: null
    classification: core
    target_package_kind: core
    target_package_id: core
    candidate_rule_id: coach.execution.atomic-registry-write
    reason: Any verb mutating the delivery-unit registry must commit that write atomically with the verb; refuse on protected mainline. Execution discipline.
    notes: git_commit_manifest_update + the .atdd/manifest.yaml path are the workspace mechanism; "registration is atomic and fails loud" is core.
  - source_file: issue.convention.yaml
    source_section: "gate_tests.universal (GT-001/002/800/850/900) + validation"
    source_rule_id: null
    classification: core
    target_package_kind: core
    target_package_id: core
    candidate_rule_id: coach.lifecycle.universal-completion-gates
    reason: Universal design/completion gates (validate, repo validate, registry sync) bound to every delivery unit. Lifecycle completion criteria.
    notes: "core_surface: toolkit_self for the concrete `atdd ...` commands. required_by_archetype + atdd_cycle gates are archetype/stack-specific -> legacy_redirect/workspace."
  - source_file: issue.convention.yaml
    source_section: "github_issue_tracking (labels, issue_types, cli_commands, hard_dependencies, wmbt_sub_issue_template, parent_issue_template)"
    source_rule_id: null
    classification: extension
    target_package_kind: extension
    target_package_id: atdd.extension.github
    candidate_rule_id: null
    reason: GitHub Issues/Labels/Projects v2/sub-issues, gh CLI hard deps, GitHub-issue-body templates. Heavy platform binding.
    notes: The three-layer (body/fields/sub-issues) model, label taxonomy, and templates all assume GitHub. cli_commands wrap GitHub.
  - source_file: issue.convention.yaml
    source_section: "status.auto_transition_on_merge.{workflow,projects_access_fallback}"
    source_rule_id: null
    classification: extension
    target_package_kind: extension
    target_package_id: atdd.extension.github
    candidate_rule_id: null
    reason: PR-merge trigger, atdd-auto-phase.yml workflow, ProjectV2 token fallback — GitHub mechanics.
    notes: Pairs with the core single-step-advance rule; this is its github realization.
  - source_file: issue.convention.yaml
    source_section: "workflow.phases.{planner,tester,coder}.{artifacts,validators,gate_command} + gate_tests.required_by_archetype + gate_tests.atdd_cycle"
    source_rule_id: null
    classification: legacy_redirect
    target_package_kind: none
    target_package_id: none
    candidate_rule_id: null
    reason: Concrete planner/tester/coder artifact paths, validators, and per-archetype gates are owned by planner/tester/coder conventions (now nodes).
    notes: Redirect to the archetype conventions; do not re-author as coach authority. db/be/fe gates also imply stack workspaces.
  - source_file: issue.convention.yaml
    source_section: "format + frontmatter_schema + filesystem + session_types + sections + status.values/transitions(ACTIVE) + rules.{creation,implementation,pattern_discovery,progression,completion,blocking,obsolete}"
    source_rule_id: null
    classification: legacy_redirect
    target_package_kind: none
    target_package_id: none
    candidate_rule_id: null
    reason: The local SESSION-NN.md file model (frontmatter, atdd-sessions/, INIT/PLANNED/ACTIVE state machine) is explicitly historical — superseded by GitHub issues + phase_machine.
    notes: The file itself labels this block "LOCAL SESSION FILES (legacy)". The ACTIVE-state machine here is NOT phase_machine; do not let it leak into core.
  - source_file: issue.convention.yaml
    source_section: "archetypes (db/be/fe/contracts/wmbt/wagon/train/telemetry/migrations/coach) + rules.supabase_branching"
    source_rule_id: null
    classification: legacy_redirect
    target_package_kind: workspace
    target_package_id: atdd.workspace.python-pytest / atdd.workspace.supabase
    candidate_rule_id: null
    reason: Archetype->artifact->validation registry; contracts/wmbt/wagon/train/telemetry redirect to planner/tester nodes; db/be/fe + supabase_branching are stack-runtime.
    notes: Mixed redirect/workspace. coach archetype self-row is core/self but already covered by other coach nodes.

  # ── pr.convention.yaml ─────────────────────────────────────────────────────
  - source_file: pr.convention.yaml
    source_section: "rules[coach.pr.runtime-artifacts-blocked]"
    source_rule_id: coach.pr.runtime-artifacts-blocked
    classification: core
    target_package_kind: core
    target_package_id: core
    candidate_rule_id: coach.execution.runtime-state-not-a-delivery-artifact
    reason: Ephemeral per-run runtime state must never be treated as a delivery artifact. Protocol abstraction over the .atdd/runtime/ + PR-diff specifics.
    notes: The PR-diff/.gitignore mechanism is github/git; the runtime!=artifact invariant is core.
  - source_file: pr.convention.yaml
    source_section: "rules[coach.pr.merge-blocks-on-pre-smoke-close] (abstract half)"
    source_rule_id: coach.pr.merge-blocks-on-pre-smoke-close
    classification: core
    target_package_kind: core
    target_package_id: core
    candidate_rule_id: coach.lifecycle.no-terminal-before-lifecycle-satisfied
    reason: A delivery unit must not be driven to a terminal/shipped state before its lifecycle requirements (through SMOKE/REFACTOR) are satisfied.
    notes: The concrete realization (closingIssuesReferences, Closes/Fixes keywords, label phases) is github extension (row below). Thin core abstraction only.
  - source_file: pr.convention.yaml
    source_section: "rules[coach.pr.green-ships-code-without-smoke; coach.pr.closes-keyword-discipline; coach.pr.merge-blocks-on-pre-smoke-close (concrete)] + phase_labels + auto_close_keywords + references"
    source_rule_id: "coach.pr.green-ships-code-without-smoke; coach.pr.closes-keyword-discipline; coach.pr.merge-blocks-on-pre-smoke-close"
    classification: extension
    target_package_kind: extension
    target_package_id: atdd.extension.github
    candidate_rule_id: null
    reason: PR body semantics, auto-close keyword set, closingIssuesReferences GraphQL field, gh commands, GitHub merge gating.
    notes: Co-locate with the two misfiled PR rules from rule-id.convention. This file is the canonical github-PR rule home.

  # ── commit-trailers.convention.yaml ────────────────────────────────────────
  - source_file: commit-trailers.convention.yaml
    source_section: "required_trailers + rules[phase-required, wmbt-urn-required, agent-id-required]"
    source_rule_id: "coach.commit-trailers.phase-required; coach.commit-trailers.wmbt-urn-required; coach.commit-trailers.agent-id-required"
    classification: workspace
    target_package_kind: workspace
    target_package_id: atdd.workspace.git-worktree
    candidate_rule_id: null
    reason: RFC-822 git trailers detected via `git interpret-trailers` by the coach git watcher — git-commit mechanics.
    notes: See design_candidate below for the protocol concept these encode.
  - source_file: commit-trailers.convention.yaml
    source_section: "rules[issue-required]"
    source_rule_id: coach.commit-trailers.issue-required
    classification: extension
    target_package_kind: extension
    target_package_id: atdd.extension.github
    candidate_rule_id: null
    reason: The Issue trailer names a GitHub issue number — platform identity.
    notes: Splits from the phase/wmbt/agent trailers which are git-mechanism + planner-URN.
  - source_file: commit-trailers.convention.yaml
    source_section: "(concept) work-provenance trailers"
    source_rule_id: null
    classification: design_candidate
    target_package_kind: none
    target_package_id: none
    candidate_rule_id: coach.execution.work-provenance
    reason: "The protocol idea — every unit of delivered work carries phase/WMBT/agent provenance — is real, but today it is 100% git+GitHub coupled."
    notes: Do NOT author as core now; abstracting provenance from git trailers needs the execution/workspace contracts. Record as follow-up.

  # ── forbidden_commands.convention.yaml ─────────────────────────────────────
  - source_file: forbidden_commands.convention.yaml
    source_section: "description(match_type/match-spec) + fail_behavior (classifier substrate)"
    source_rule_id: null
    classification: design_candidate
    target_package_kind: none
    target_package_id: none
    candidate_rule_id: coach.execution.command-policy-classifier
    reason: The fail-open command-policy classifier (hard_block/loop_block, match spec, fail-open-on-load-error) is reusable enforcement substrate.
    notes: The substrate could be core; the concrete patterns are platform. No standalone normative rule today -> record as design_candidate, keep substrate in legacy until a home exists.
  - source_file: forbidden_commands.convention.yaml
    source_section: "patterns[ATDD-FORBID-GH-ISSUE-CREATE, ATDD-FORBID-GH-PR-CREATE, ATDD-LOOP-GH-PR-POLL]"
    source_rule_id: "ATDD-FORBID-GH-ISSUE-CREATE; ATDD-FORBID-GH-PR-CREATE; ATDD-LOOP-GH-PR-POLL"
    classification: extension
    target_package_kind: extension
    target_package_id: atdd.extension.github
    candidate_rule_id: null
    reason: gh issue/pr create + gh pr poll rate-limit — GitHub/gh platform behavior.
    notes: null
  - source_file: forbidden_commands.convention.yaml
    source_section: "patterns[ATDD-FORBID-CMUX-SEND-CLAUDE, ATDD-FORBID-GIT-CONFIG-BARE-UNSCOPED]"
    source_rule_id: "ATDD-FORBID-CMUX-SEND-CLAUDE; ATDD-FORBID-GIT-CONFIG-BARE-UNSCOPED"
    classification: workspace
    target_package_kind: workspace
    target_package_id: "atdd.workspace.cmux-claude; atdd.workspace.git-worktree"
    candidate_rule_id: null
    reason: cmux send-with-claude cwd-bleed and git config core.bare contamination — runtime transport + git-worktree safety.
    notes: Two different workspace providers; split when packaging.

  # ── path_shim_gh.convention.yaml ───────────────────────────────────────────
  - source_file: path_shim_gh.convention.yaml
    source_section: "patterns[ATDD-SHIM-GH-ISSUE-CREATE, ATDD-PRECOMMIT-GH-ISSUE-CREATE]"
    source_rule_id: "ATDD-SHIM-GH-ISSUE-CREATE; ATDD-PRECOMMIT-GH-ISSUE-CREATE"
    classification: extension
    target_package_kind: extension
    target_package_id: atdd.extension.github
    candidate_rule_id: null
    reason: .atdd/bin/gh PATH shim + pre-commit grep enforcing the gh-issue-create block across harnesses. GitHub-specific.
    notes: Harness-agnostic enforcement sites, but the thing enforced is a GitHub command.

  # ── path_shim_git.convention.yaml ──────────────────────────────────────────
  - source_file: path_shim_git.convention.yaml
    source_section: "patterns[ATDD-SHIM-GIT-CONFIG-BARE-UNSCOPED]"
    source_rule_id: ATDD-SHIM-GIT-CONFIG-BARE-UNSCOPED
    classification: workspace
    target_package_kind: workspace
    target_package_id: atdd.workspace.git-worktree
    candidate_rule_id: null
    reason: .atdd/bin/git PATH shim blocking unscoped core.bare/core.worktree/core.hooksPath writes — git-worktree isolation safety.
    notes: null

  # ── spawn.convention.yaml ──────────────────────────────────────────────────
  - source_file: spawn.convention.yaml
    source_section: "rules[coach.spawn.atdd-spawn-cli]"
    source_rule_id: coach.spawn.atdd-spawn-cli
    classification: workspace
    target_package_kind: workspace
    target_package_id: atdd.workspace.cmux-claude
    candidate_rule_id: null
    reason: Every persona launch flows through `atdd spawn` (renders prompt, dispatches multiplexer, runs per-LLM adapter, emits agent_spawned). cmux+Claude launch path.
    notes: The "one rule-IDed entry point owns the launch path" idea is a workspace-contract concept; the entry point itself is runtime.

  # ── naming.convention.yaml ─────────────────────────────────────────────────
  - source_file: naming.convention.yaml
    source_section: "patterns.{wagon,feature,contract,telemetry,train,acceptance,wmbt} + separator_semantics + rules[coach.naming.separator/format/urn] + validation_summary + references"
    source_rule_id: "coach.naming.separator; coach.naming.format; coach.naming.urn"
    classification: legacy_redirect
    target_package_kind: none
    target_package_id: none
    candidate_rule_id: null
    reason: Per-archetype naming patterns + separator grammar now authored as planner/tester nodes (artifact-naming, wagon, feature, train, acceptance, wmbt, contract, telemetry). Coach must not duplicate that authority.
    notes: This is the canonical "naming.convention is a master registry that should redirect after planner decomposition" case from #1113. Verify the colon/dot/hyphen grammar exists in planner.artifact-naming nodes; if not, raise a planner gap (do not retain in coach).
  - source_file: naming.convention.yaml
    source_section: "patterns.{appendix,system}"
    source_rule_id: null
    classification: core
    target_package_kind: core
    target_package_id: core
    candidate_rule_id: coach.role.cross-cutting-urn-types
    reason: "appendix: and system: URN types are cross-cutting (not owned by any planner archetype) and currently unenforced — the only genuinely coach-retained naming material."
    notes: Low priority / thin. Could equally be deferred as design_candidate if Slice-2 review prefers; flagged for the reviewer.
```

---

## Per-file judgment notes

- **`phase_machine`** is the cleanest core file and the anchor for `coach.lifecycle.*`.
  Everything else's lifecycle claims should reference it rather than restate it.
- **The lifecycle is split across three files today:** `phase_machine` (the state
  machine), `issue.convention.workflow` (role sequence + completion), and
  `issue.convention.status` (a *second, stale* INIT/PLANNED/ACTIVE machine). Slice 2
  must converge on `phase_machine` + the `workflow` core rows and explicitly retire
  the `status` ACTIVE-state machine as legacy — it is the highest leakage risk.
- **`issue.convention` is the hardest file:** ~40KB, ~5 genuinely-core sections
  buried in heavy GitHub binding and a fully-legacy local-session-file model. The
  rows split it five ways; the GitHub material is the bulk of `atdd.extension.github`.
- **`pr.convention` keeps only two thin core abstractions**; everything keyword/
  closingIssuesReferences/label-phase is github. The two misfiled PR rules in
  `rule-id.convention` belong here too.
- **`commit-trailers` deliberately keeps nothing in core.** The provenance idea is
  real but git+GitHub-coupled; promoting it now would freeze git into the protocol.
  Recorded as `coach.execution.work-provenance` design_candidate instead.
- **`naming` is mostly legacy_redirect** — the post-#1108 planner nodes own the
  per-archetype grammar. Only `appendix`/`system` URN types are arguably coach-owned,
  and even those are flagged for reviewer confirmation.

## design_candidate follow-ups (record, do NOT author as nodes)

| candidate_id | source hint | recommended follow-up |
|--------------|-------------|------------------------|
| `coach.execution.work-provenance` | commit-trailers | Define provenance abstractly once the execution + git-worktree workspace contracts exist; bind git trailers as one realization. |
| `coach.execution.command-policy-classifier` | forbidden_commands substrate | Define the fail-open command-policy classifier as core enforcement substrate; platform patterns stay in extensions. |
| `coach.workspace.freedom-set-declared-as-data` | session freedom_layer (E031) | Make "freedom set is data read by launch planes" a workspace-provider contract rule once that contract exists. |
| `coach.execution.*` (instance, binding, invocation, result-capture, resume) | aligned model §5 | No legacy source yet; author first real node when the coach execution schema is defined (Slice 3+). |
| `coach.extension.*` / `coach.workspace.*` (manifest, composition, contract-version, conformance) | aligned model §5 | Backed by the #1097 author substrate, not by coach legacy text; author when packages are built. |

## Non-core migration targets (Slice 3 backlog seeds)

| Target package | Receives | From |
|----------------|----------|------|
| `atdd.extension.github` | issues/labels/Projects/sub-issues/templates, PR rules, gh shims, gh forbidden-commands, issue trailer, auto-phase workflow | issue, pr, rule-id (2 PR rules), path_shim_gh, forbidden_commands, commit-trailers (issue), issue.status |
| `atdd.workspace.git-worktree` | git-config-bare shim + forbidden pattern, commit-trailer git mechanics, worktree isolation | path_shim_git, forbidden_commands, commit-trailers |
| `atdd.workspace.cmux-claude` | cmux launch/Feed transport, cli-return, session naming/layout drift, bash classifier, token threshold, spawn entry, cmux forbidden pattern | coach, session, observer, spawn, forbidden_commands |
| `atdd.workspace.python-pytest` (+ `supabase`) | stack root defaults/resolvers, db/be/fe archetype gates, supabase branching | code-roots, issue.archetypes |

> Targets are provisional. Slice 3 files one follow-up issue per package; nothing
> here is built in the Slice-2 core-parity PR.
