# Convention Validator Parity Audit (#1205)

Deterministic map of every legacy persona validator to the #1204 convention-graph family/template architecture.

- Total entries (validators): **237**
- Total excluded (helpers): **30**
- Files accounted: **267**

## Rollups

- by parity_status: {'direct': 92, 'extension_candidate': 9, 'merged': 10, 'not_convention_graph': 86, 'split': 36, 'superseded': 4}
- by priority: {'P0': 36, 'P1': 71, 'P2': 130}
- by proposed_family: {'acyclicity': 1, 'binding': 7, 'boundary': 11, 'coherence': 9, 'composition': 1, 'coverage': 18, 'extension_candidate': 9, 'grammar': 16, 'non_convention': 86, 'policy': 29, 'presence': 20, 'resolution': 10, 'schema': 5, 'sizing': 13, 'uniqueness': 2}

## planner (31 validators, 4 excluded)

| validator | family/template | status | priority | notes |
|---|---|---|---|---|
| test_custom_themes_schema.py | non_convention | not_convention_graph | P2 | Asserts the JSON Schema *files* declare a kebab pattern rather than an enum (#291 config f |
| test_custom_themes.py | non_convention | not_convention_graph | P2 | Exercises runtime config.yaml theme-map loading/merging behaviour (#291); tooling/config-r |
| test_dispatch_registry.py | schema/node_schema_conformance | split | P0 | Two bound rules: dispatch-map-is-registry (schema/node_schema_conformance of the registry  |
| test_draft_wagon_registry.py | resolution/artifact_reference_resolution | split | P0 | Bundles three questions: duplicate detection (uniqueness/scoped_identifier_uniqueness), ar |
| test_feedback_loop_smoke_closes_the_loop.py | presence/conditional_requirement | direct | P1 | Conditional requirement: IF feature kind == feedback-loop THEN a SMOKE acceptance must car |
| test_hierarchy_coverage.py | coverage/source_has_required_target | direct | P1 | Bound rule every-wmbt-must-have is source_has_required_target; the docstring's full bidire |
| test_issue_body_has_graph_context.py | non_convention | not_convention_graph | P2 | Enforces presence of a section in GitHub issue body text — operational issue-tracking meta |
| test_issue_deps_have_classification_tags.py | non_convention | not_convention_graph | P2 | Enforces classification tags in GitHub issue body dependency lines — operational issue-tra |
| test_no_cross_wagon_consume_cycle.py | acyclicity/forbidden_cycle_absence | direct | P1 | Cycle detection over the produce->consume wagon graph; single acyclicity/forbidden_cycle_a |
| test_no_orphan_nodes.py | coverage/reachability_no_orphan | direct | P1 | Every convention node must be reachable as an edge endpoint; canonical reachability_no_orp |
| test_plan_confirm_before_author.py | non_convention | not_convention_graph | P2 | Behavioural runtime gate exercising the live PlanSession author pass (#1139); enforces a s |
| test_plan_confirm_binds_issue.py | non_convention | not_convention_graph | P2 | Behavioural runtime gate on PlanSession.confirm() (#1171); enforces session/issue-binding  |
| test_plan_cross_refs.py | resolution/artifact_reference_resolution | direct | P0 | Consume->produce artifact reference resolution across wagons/trains; canonical artifact_re |
| test_plan_uniqueness.py | uniqueness/scoped_identifier_uniqueness | direct | P0 | Scoped identifier uniqueness for wagon slugs / train IDs / WMBT IDs; canonical scoped_iden |
| test_plan_urn_resolution.py | resolution/artifact_reference_resolution | direct | P0 | URN->filesystem artifact resolution for contracts/telemetry; canonical artifact_reference_ |
| test_plan_wagons.py | schema/node_schema_conformance | direct | P0 | Per-wagon jsonschema conformance against wagon.schema.json; canonical node_schema_conforma |
| test_smoke_synthetic_fixture_bypass.py | policy/forbidden_construct_absence | direct | P2 | Forbidden-construct scan over SMOKE test file source (#855); a policy/forbidden_construct_ |
| test_theme_archetype_alignment.py | coherence/resolved_fact_agreement | direct | P1 | Two facts must agree: declared theme vs. actual archetype source root of the wagon's imple |
| test_theme_commons_coach_boundary.py | boundary/allowed_boundary_crossing | direct | P1 | Import/layer boundary: commons wagons may not import atdd.coach; canonical allowed_boundar |
| test_theme_must_be_canonical.py | grammar/identifier_grammar_conformance | direct | P0 | Theme token must be a member of the canonical vocabulary (retired digits 5-9 and undeclare |
| test_theme_urn_namespace_matches.py | coherence/resolved_fact_agreement | direct | P1 | Two facts must agree: produced-URN theme prefix vs. wagon's declared theme; canonical reso |
| test_theme_zero_mandatory.py | presence/required_field_presence | direct | P1 | Mandatory presence of the commons floor (digit 0) in every resolved theme set regardless o |
| test_train_family_matches_terminal_contract.py | coherence/resolved_fact_agreement | direct | P1 | Two facts must agree: declared train family vs. terminal-contract artifact; canonical reso |
| test_train_validation.py | resolution/direct_reference_resolution | split | P0 | Bundles many questions: wagon-reference resolution (direct_reference_resolution), theme nu |
| test_wagon_coupling_complexity.py | sizing/cardinality_bounds | direct | P1 | Cardinality/threshold bound on a coupling metric over the produce->consume graph; advisory |
| test_wagon_separability.py | sizing/cardinality_bounds | direct | P1 | Threshold/bound on a cohesion-vs-coupling metric over the WMBT graph; advisory non-blockin |
| test_wagon_urn_chain.py | resolution/reference_chain_resolution | direct | P0 | Recursive multi-hop URN chain reconciliation with no inference; canonical reference_chain_ |
| test_wmbt_consistency.py | coherence/resolved_fact_agreement | direct | P1 | Declared WMBT references must agree with the filesystem WMBT YAML set (source of truth); c |
| test_wmbt_has_smoke_acceptance.py | coverage/source_has_required_target | direct | P1 | Every WMBT (source) must have at least one SMOKE acceptance (required target); canonical s |
| test_wmbt_smoke_acceptance_rule_registered.py | binding/declaration_to_implementation_binding | superseded | P0 | Asserts a single rule_id is registered in its convention's rules block — a one-off instanc |
| test_wmbt_vocabulary.py | grammar/identifier_grammar_conformance | direct | P0 | Controlled-vocabulary + statement-pattern conformance for WMBT fields (authorized step cod |

**Excluded helpers:**

- `src/atdd/planner/validators/__init__.py` — Package marker, not an executable validator.
- `src/atdd/planner/validators/conftest.py` — pytest support file (shared fixtures), not an executable validator.
- `src/atdd/planner/validators/_theme_taxonomy.py` — Leading-underscore shared helper module (theme taxonomy constants), imported by theme validators.
- `src/atdd/planner/validators/_wagon_cohesion.py` — Leading-underscore shared helper module (wagon cohesion/coupling graph math), imported by separability validator.

## tester (44 validators, 9 excluded)

| validator | family/template | status | priority | notes |
|---|---|---|---|---|
| test_acceptance_disposition.py | policy/forbidden_construct_absence | direct | P1 | Pure forbidden-construct check over acceptance nodes; one bound rule, one target. |
| test_acceptance_measurable.py | presence/conditional_requirement | direct | P1 | Conditional field requirement (one-of enforcement) on acceptance nodes. |
| test_acceptance_phase.py | presence/required_field_presence | direct | P1 | Required field presence on acceptance node (enum value constraint is incidental). |
| test_acceptance_urn_filename_mapping.py | non_convention | not_convention_graph | P2 | Unit test of a pure generator function (URN→filename), not repo-graph enforcement. |
| test_acceptance_urn_separator.py | grammar/identifier_grammar_conformance | direct | P0 | Core identifier grammar of acceptance URNs. |
| test_artifact_naming_category.py | grammar/identifier_grammar_conformance | direct | P0 | Identifier grammar conformance over artifact names. |
| test_contract_schema_compliance.py | schema/node_schema_conformance | direct | P0 | Node schema conformance of contract nodes against meta-schema. |
| test_contract_security.py | presence/conditional_requirement | split | P1 | Bundles conditional field presence (auth/security) and SEC/RLS coverage; needs ≥2 targets. |
| test_contracts_structure.py | grammar/identifier_grammar_conformance | direct | P0 | Path/name grammar conformance for the contracts directory. |
| test_coverage_adequacy.py | coverage/source_has_required_target | split | P1 | Combines per-acceptance target coverage with numeric threshold (cardinality) checks. |
| test_dual_ac_reference.py | presence/required_field_presence | direct | P1 | Required presence of the acceptance reference in two declared locations of a test file. |
| test_fixture_validity.py | schema/node_schema_conformance | split | P1 | Schema conformance of fixtures plus a separate realism/forbidden-data check. |
| test_hermetic_integration_contract.py | presence/conditional_requirement | direct | P1 | Conditional requirement: permitted_fakes present implies hermetic block declared. |
| test_hermetic_live_smoke_pairing.py | presence/required_relationship_presence | direct | P1 | Requires a paired related acceptance node (relationship presence). |
| test_hierarchy_coverage.py | coverage/source_has_required_target | split | P1 | Bundles three distinct binding/coverage questions; needs separate targets per edge type. |
| test_isolation.py | policy/forbidden_construct_absence | merged | P2 | Overlaps the bound no-polluting-patterns isolation check; should collapse into that target |
| test_live_smoke_execution.py | policy/forbidden_construct_absence | direct | P1 | Forbidden self-skip construct in live_smoke tests; one bound rule. |
| test_locale_coverage.py | extension_candidate | extension_candidate | P2 | i18n/locale concern; belongs in an app/workspace extension, not the core convention graph. |
| test_metric_implementation.py | resolution/artifact_reference_resolution | direct | P0 | Metric reference must resolve to an existing implementation artifact (file/function). |
| test_migration_coverage.py | coverage/source_has_required_target | direct | P1 | Each persistence-requiring contract must have a migration target. |
| test_migration_criteria.py | non_convention | not_convention_graph | P2 | Unit test of a decision function's logic, not repo-graph enforcement. |
| test_migration_generation.py | non_convention | not_convention_graph | P2 | Unit test of an unimplemented generator function; not graph enforcement. |
| test_no_polluting_patterns.py | policy/forbidden_construct_absence | direct | P1 | AST forbidden-construct scan; one bound rule, one target. |
| test_presentation_has_behavioral_test.py | extension_candidate | extension_candidate | P2 | Web presentation-layer concern; belongs in an app/frontend extension. |
| test_presentation_smoke_coverage.py | extension_candidate | extension_candidate | P2 | Web/e2e frontend concern; belongs in an app/frontend extension. |
| test_python_test_naming.py | grammar/identifier_grammar_conformance | direct | P0 | Identifier/filename grammar conformance for Python test files. |
| test_red_layer_validation.py | grammar/identifier_grammar_conformance | split | P1 | General 4-layer path-structure check that subsumes the python+supabase layer variants. |
| test_red_python_layer_structure.py | grammar/identifier_grammar_conformance | direct | P1 | Path-layout grammar for the Python 4-layer test tree. |
| test_red_supabase_layer_structure.py | grammar/identifier_grammar_conformance | direct | P1 | Path-layout grammar for the Supabase 4-layer test tree. |
| test_repo_validator_binding.py | binding/declaration_to_implementation_binding | direct | P0 | Bidirectional declaration↔implementation binding; foundational rule-validator correctness. |
| test_security_ref_binding.py | resolution/direct_reference_resolution | split | P0 | Bundles abuse_case reference resolution and pytest-anchor binding; needs resolution + bind |
| test_smoke_coverage.py | coverage/source_has_required_target | split | P1 | Combines smoke-coverage requirement with a forbidden-mock-import policy check. |
| test_smoke_no_collaborator_substitution.py | policy/forbidden_construct_absence | direct | P1 | Forbidden-construct scan over SMOKE tests; one bound rule. |
| test_telemetry_structure.py | grammar/identifier_grammar_conformance | direct | P0 | Identifier/filename grammar for telemetry signal files. |
| test_train_backend_e2e.py | grammar/identifier_grammar_conformance | direct | P1 | Path/name grammar for backend E2E test files (marker presence is incidental). |
| test_train_completeness.py | coverage/source_has_required_target | split | P1 | Superset chain that subsumes train-e2e-existence and train-route-smoke-coverage. |
| test_train_e2e_existence.py | coverage/source_has_required_target | direct | P1 | Each registered train must have an E2E test target. |
| test_train_frontend_e2e.py | extension_candidate | extension_candidate | P2 | Frontend/web E2E concern; belongs in an app/frontend extension. |
| test_train_frontend_python.py | extension_candidate | extension_candidate | P2 | Streamlit/app frontend concern; belongs in an app/frontend extension. |
| test_train_renders_content.py | extension_candidate | extension_candidate | P2 | App-layer behavioral DOM render check; belongs in an app/frontend extension, not the graph |
| test_train_route_smoke_coverage.py | coverage/source_has_required_target | direct | P1 | Each registered train must have a smoke-test target. |
| test_typescript_test_naming.py | grammar/identifier_grammar_conformance | direct | P0 | Identifier/filename grammar conformance for TypeScript test files. |
| test_typescript_test_structure.py | presence/conditional_requirement | split | P1 | Bundles required URN-header presence and a JSX⇒.test.tsx conditional extension rule. |
| test_urn_spec_v3.py | grammar/identifier_grammar_conformance | split | P0 | Bundles URN grammar with uniqueness, mutual-exclusion, enum and conditional-presence rules |

**Excluded helpers:**

- `src/atdd/tester/validators/__init__.py` — Package init module, not an executable validator.
- `src/atdd/tester/validators/_acceptance_walker.py` — Leading-underscore shared helper: raw plan/ acceptance walker used by validators.
- `src/atdd/tester/validators/_no_polluting_patterns.py` — Leading-underscore shared helper: AST scanner imported by test_no_polluting_patterns.py.
- `src/atdd/tester/validators/cleanup_duplicate_headers_v2.py` — One-off maintenance script that rewrites duplicate header comments; not a validator.
- `src/atdd/tester/validators/cleanup_duplicate_headers.py` — One-off maintenance script that cleans up duplicate header comments; not a validator.
- `src/atdd/tester/validators/conftest.py` — pytest support file re-exporting shared fixtures, not an executable validator.
- `src/atdd/tester/validators/coverage_gap_report.py` — Reporting/diagnostic script that prints coverage gaps; not an enforcing validator.
- `src/atdd/tester/validators/fix_dual_ac_references.py` — One-off fixer script that auto-repairs dual AC reference violations; not a validator.
- `src/atdd/tester/validators/remove_duplicate_lines.py` — One-off maintenance script that removes consecutive duplicate lines; not a validator.

## coder (50 validators, 7 excluded)

| validator | family/template | status | priority | notes |
|---|---|---|---|---|
| test_commons_structure.py | boundary/allowed_boundary_crossing | split | P2 | Architectural import-boundary check on consumer code (commons.convention.yaml); bundles do |
| test_complexity_typescript.py | sizing/cardinality_bounds | split | P1 | Three threshold (max-bound) rules; each is a cardinality_bounds variant so splits into per |
| test_complexity.py | sizing/cardinality_bounds | split | P1 | Five threshold rules; each maps to a cardinality_bounds variant so splits into per-metric  |
| test_composition_completeness.py | coverage/source_has_required_target | split | P1 | Every consumer must have a wiring target (composition root); two rules (consumer + root) s |
| test_contract_driven_http.py | boundary/allowed_boundary_crossing | direct | P2 | Single boundaries.convention rule constraining how the http-client boundary may be crossed |
| test_cross_language_consistency.py | coherence/resolved_fact_agreement | split | P1 | Same fact must agree across two language stacks; four rules split into per-fact coherence  |
| test_dead_code_python.py | coverage/reachability_no_orphan | direct | P1 | Reachability/orphan check on the Python call graph — maps cleanly to reachability_no_orpha |
| test_dead_code_typescript.py | coverage/reachability_no_orphan | direct | P1 | TypeScript parity of dead-code-python; reachability/orphan check maps to reachability_no_o |
| test_design_system_compliance.py | extension_candidate | extension_candidate | P2 | Consumer-app design-system convention (tokens/primitives/foundations); belongs in a UX wor |
| test_dto_testing_patterns.py | policy/forbidden_construct_absence | direct | P2 | Forbids the `assert entity in dtos` antipattern (dto.convention.yaml) — single forbidden-c |
| test_duplication_detector_typescript.py | policy/forbidden_construct_absence | direct | P2 | Forbids intra-layer code duplication (TypeScript) — single forbidden-construct rule. |
| test_duplication_detector.py | policy/forbidden_construct_absence | direct | P2 | Forbids intra-layer code duplication (Python) — single forbidden-construct rule. |
| test_error_response_compliance.py | policy/forbidden_construct_absence | split | P2 | Bare-string rule is forbidden_construct_absence; code-format rule is closer to grammar — s |
| test_frontend_composition_root.py | presence/required_relationship_presence | direct | P1 | SPEC-CODER-TRAIN-0001: composition-root node must exist and declare its required method su |
| test_frontend_security_patterns.py | policy/forbidden_construct_absence | direct | P2 | Forbids a known-bad construct (innerHTML) per security.convention.yaml; emits SECURITY-XSS |
| test_god_hook_elimination.py | sizing/cardinality_bounds | direct | P1 | SPEC-CODER-PAGE-0003: hook line-count upper bound with allowlist — cardinality_bounds. |
| test_green_cross_stack_layers.py | coherence/resolved_fact_agreement | direct | P1 | SPEC-CODER-CONV-0019: the same layer-name fact must agree across all stacks declared in th |
| test_green_layer_dependencies.py | presence/required_field_presence | direct | P1 | SPEC-CODER-CONV-0018: asserts the convention node declares required dependency-rule fields |
| test_green_python_layer_structure.py | presence/required_field_presence | direct | P1 | SPEC-CODER-CONV-0015: asserts the convention node declares the required 4-layer Python str |
| test_green_supabase_layer_structure.py | presence/required_field_presence | split | P1 | SPEC-CODER-CONV-0017: 4-layer-structure presence plus the no-business-logic-in-index.ts ru |
| test_gsap_layer_usage.py | extension_candidate | extension_candidate | P2 | App-specific animation-library (GSAP) layering convention; belongs in a frontend/UX worksp |
| test_hierarchy_coverage.py | coverage/source_has_required_target | split | P1 | every-feature/every-implementation must-have rules are source_has_required_target; three r |
| test_i18n_runtime.py | extension_candidate | extension_candidate | P2 | App-specific internationalization runtime convention; belongs in a frontend/UX workspace e |
| test_import_boundaries.py | boundary/allowed_boundary_crossing | split | P2 | Import-flow boundary check; also bundles a circular-dependency check (acyclicity/forbidden |
| test_init_file_urns.py | grammar/identifier_grammar_conformance | direct | P0 | Validates URN format component:{wagon}:{feature}:{name}:{side}:{layer} on init/barrel file |
| test_no_silent_exception_swallowing_python.py | policy/forbidden_construct_absence | direct | P2 | Forbids the silent-swallow construct (logging.convention.yaml) — single forbidden-construc |
| test_no_silent_exception_swallowing_typescript.py | policy/forbidden_construct_absence | direct | P2 | TypeScript parity (COACH-SILENT-SWALLOW-001); forbids the silent-swallow construct — singl |
| test_no_stub_presentation_returns.py | policy/forbidden_construct_absence | direct | P2 | PRESENTATION-NOSTUB-00x: forbids stub render bodies; single concern with multiple detected |
| test_page_elimination.py | policy/forbidden_construct_absence | split | P2 | SPEC-CODER-PAGE-0001/0002/0005/0010/0011: forbids non-allowlisted page files plus migratio |
| test_preact_layer_boundaries.py | boundary/allowed_boundary_crossing | split | P2 | SPEC-CODER-ARCH-PREACT-001..004: multiple per-layer crossing rules; splits into boundary v |
| test_presentation_convention.py | boundary/allowed_boundary_crossing | split | P2 | Script-style validator bundling controller structure + pydantic/contract alignment + compo |
| test_presentation_ratchet_requires_smoke.py | coverage/source_has_required_target | direct | P1 | Every ratchet entry must have a required SMOKE target — source_has_required_target. |
| test_python_architecture.py | boundary/allowed_boundary_crossing | split | P2 | backend.convention.yaml clean-architecture enforcement; bundles per-layer crossing rules s |
| test_quality_metrics_typescript.py | sizing/cardinality_bounds | split | P1 | MI and comment-ratio threshold rules — each a cardinality_bounds variant. |
| test_quality_metrics.py | sizing/cardinality_bounds | split | P1 | Five quality-threshold rules (MI/comments/duplication/naming/file-length); predominantly c |
| test_query_count.py | sizing/cardinality_bounds | direct | P1 | Query-count upper-bound (N+1) check — cardinality_bounds, single rule. |
| test_route_train_compliance.py | policy/forbidden_construct_absence | direct | P2 | SPEC-CODER-PAGE-0004: forbids direct page-component imports in routes — single forbidden-c |
| test_route_train_wagon_coverage.py | resolution/reference_chain_resolution | direct | P0 | Route -> Train -> Wagon multi-hop reference chain must resolve end-to-end — reference_chai |
| test_security_patterns.py | policy/forbidden_construct_absence | split | P2 | Three forbidden security constructs (sql-injection/missing-auth/hardcoded-secret); each a  |
| test_station_master_pattern.py | coverage/source_has_required_target | split | P1 | Each wagon must have required composition delegation/direct-adapter targets; bundles three |
| test_structured_logging.py | policy/forbidden_construct_absence | split | P2 | no-print rule is forbidden_construct_absence; structured-logging-shape rule is a presence  |
| test_train_composition_smoke.py | non_convention | not_convention_graph | P2 | SMOKE integration harness exercising the train_composition validator trio against a fixtur |
| test_train_infrastructure.py | presence/required_relationship_presence | split | P1 | Train First-Class Spec: several required-infrastructure relationships must exist; splits i |
| test_train_urns.py | grammar/identifier_grammar_conformance | split | P0 | Primary check is train:{theme}:{train_id} URN grammar; also resolves train IDs to specs (r |
| test_train_yaml_render_metadata.py | schema/node_schema_conformance | direct | P0 | SPEC-CODER-TRAIN-0003: validates each train YAML node against a JSON Schema — node_schema_ |
| test_typescript_architecture.py | boundary/allowed_boundary_crossing | split | P2 | TypeScript parity of python-clean-architecture; bundles per-layer crossing rules so splits |
| test_usecase_structure.py | boundary/allowed_boundary_crossing | split | P2 | Primary rule is the no-direct-DB/port-coordination boundary; also bundles execute-method p |
| test_wagon_boundaries_typescript.py | boundary/allowed_boundary_crossing | direct | P2 | Cross-wagon access must cross only via barrel exports — allowed_boundary_crossing (composi |
| test_wagon_boundaries.py | boundary/allowed_boundary_crossing | split | P2 | SPEC-BOUNDARIES-0001: qualified-import boundary plus packaging/pythonpath checks — primary |
| test_wagon_trains_export_shape.py | presence/required_relationship_presence | direct | P1 | SPEC-CODER-TRAIN-0002: trains.ts must exist and declare every required export — required_r |

**Excluded helpers:**

- `src/atdd/coder/validators/__init__.py` — package marker, not an executable validator
- `src/atdd/coder/validators/_ast_tsx.py` — leading-underscore shared helper: TSX/AST parsing utilities used by validators
- `src/atdd/coder/validators/_four_tier_ratchet.py` — leading-underscore shared helper: four-tier ratchet/disposition framework used by validators
- `src/atdd/coder/validators/_toolkit_roots.py` — leading-underscore shared helper: toolkit scan-root resolution used by validators
- `src/atdd/coder/validators/conftest.py` — pytest support file, not an executable validator
- `src/atdd/coder/validators/presentation_ratchet.py` — non-test_ shared helper: presentation-ratchet baseline logic imported by test_presentation_ratchet_requires_smoke.py
- `src/atdd/coder/validators/route_train_wagon_analyzer.py` — non-test_ shared helper: route/train/wagon analysis logic imported by test_route_train_wagon_coverage.py

## coach (112 validators, 10 excluded)

| validator | family/template | status | priority | notes |
|---|---|---|---|---|
| test_api_validators_marked_github_api.py | non_convention | not_convention_graph | P2 | Meta-validator over pytest marker hygiene of validator modules; tooling shape, not a conve |
| test_auto_phase_workflow_exists.py | non_convention | not_convention_graph | P2 | Asserts a CI workflow artifact exists; CI/runtime shape, not a convention-graph node. |
| test_branch_protection.py | non_convention | not_convention_graph | P2 | Evaluates live GitHub repo settings; runtime governance, not convention graph. |
| test_C001_roundtrip.py | non_convention | not_convention_graph | P2 | End-to-end CLI lifecycle round-trip; runtime behavior, not convention graph. |
| test_canonical_role_naming.py | non_convention | not_convention_graph | P2 | Subject is runtime session/worktree role names, not convention-graph identifiers; advisory |
| test_cleanup_command.py | non_convention | not_convention_graph | P2 | CLI behavior test; runtime shape, not convention graph. |
| test_commit_trailers_binding.py | binding/declaration_to_implementation_binding | superseded | P0 | Per-family bind_rule binding assertion; absorbed by the generic declaration_to_implementat |
| test_composition_data_shipped.py | composition/composed_graph_loads | direct | P0 | Guards that the shipped package data lets the composed convention graph load; maps to comp |
| test_conductor_md_no_duplicated_convention.py | policy/forbidden_construct_absence | direct | P2 | Forbids duplicated convention declarations in the template; forbidden-construct-absence ov |
| test_config_themes.py | non_convention | not_convention_graph | P2 | Validates runtime config.yaml shape, not a convention-graph node schema. |
| test_core_bare_self_heal.py | non_convention | not_convention_graph | P2 | Git runtime self-heal behavior, not convention graph. |
| test_custom_theme_validation.py | non_convention | not_convention_graph | P2 | Runtime/config theme validation, not a convention-graph question. |
| test_d001_unit_001_six_schemas_exist.py | non_convention | not_convention_graph | P2 | Asserts coach runtime payload schemas exist/parse; runtime contract artifacts, not convent |
| test_d001_unit_002_fixtures_validate.py | non_convention | not_convention_graph | P2 | Validates coach runtime-schema fixtures, not convention-graph node schema. |
| test_d002_unit_001_review_report_schema_committed.py | non_convention | not_convention_graph | P2 | Coach review-report runtime schema artifact presence, not convention graph. |
| test_d002_unit_001_runtime_layout_doc_committed.py | non_convention | not_convention_graph | P2 | Documentation-artifact presence check, not convention graph. |
| test_d002_unit_002_pass_blocked_when_ac_not_covered.py | non_convention | not_convention_graph | P2 | Coach review-report intake logic, runtime behavior, not convention graph. |
| test_d002_unit_003_pass_blocked_with_strict_finding.py | non_convention | not_convention_graph | P2 | Coach review-report intake logic, runtime behavior, not convention graph. |
| test_d002_unit_004_rule_id_severity_matches_registry.py | coherence/resolved_fact_agreement | direct | P1 | Two sources (review-report finding vs registry binding) must agree on severity/disposition |
| test_d003_unit_001_five_phase_reviewer_prompts.py | non_convention | not_convention_graph | P2 | Reviewer prompt-template artifacts, not convention-graph nodes. |
| test_d003_unit_001_validator_invocation_doc_committed.py | non_convention | not_convention_graph | P2 | Documentation-artifact presence check, not convention graph. |
| test_d004_unit_001_event_semantics_doc_complete.py | non_convention | not_convention_graph | P2 | Documentation-artifact completeness check, not convention graph. |
| test_doctor_environment_diagnosis.py | non_convention | not_convention_graph | P2 | CLI environment-diagnosis behavior, not convention graph. |
| test_e001_unit_001_spawn_cli_launches_session.py | binding/declaration_to_implementation_binding | superseded | P0 | Structural per-rule bind_rule assertion; absorbed by the generic declaration_to_implementa |
| test_e003_integration_001_block_verdict_fails_the_workflow.py | non_convention | not_convention_graph | P2 | CI review-gate workflow behavior, not convention graph. |
| test_e003_integration_002_annotate_verdict_passes_with_comment.py | non_convention | not_convention_graph | P2 | CI review-gate workflow behavior, not convention graph. |
| test_e003_unit_001_workflow_file_exists_with_correct_triggers.py | non_convention | not_convention_graph | P2 | CI workflow artifact shape, not convention graph. |
| test_e005_integration_001_init_emits_only_parseable_atdd_commands.py | non_convention | not_convention_graph | P2 | CLI command drift between emitted templates and live argparse; runtime/CLI shape, not conv |
| test_e005_integration_002_drift_validator_fires_in_validate_coach.py | non_convention | not_convention_graph | P2 | CLI command-drift validator wiring; runtime/CLI shape, not convention graph. |
| test_e005_smoke_001_real_validate_coach_runs_extended_drift_validator.py | non_convention | not_convention_graph | P2 | Live CLI drift smoke; runtime/CLI shape, not convention graph. |
| test_e005_unit_001_drift_scan_captures_all_atdd_lines.py | non_convention | not_convention_graph | P2 | CLI drift-scan helper unit; runtime/CLI shape, not convention graph. |
| test_e005_unit_002_drift_validator_flags_unknown_subcommand.py | non_convention | not_convention_graph | P2 | CLI subcommand-drift validator unit; runtime/CLI shape, not convention graph. |
| test_e009_runtime_artifacts_blocked.py | non_convention | not_convention_graph | P2 | Evaluates live PR diff against GitHub; runtime governance, not convention-graph enforcemen |
| test_e009_unit_001_convention_declares_runtime_artifacts_rule.py | binding/declaration_to_implementation_binding | superseded | P0 | Asserts the convention declares + binds the rule; absorbed by the generic declaration_to_i |
| test_e022_smoke_001_live_claude_md_contains_no_atdd_skip_references.py | policy/forbidden_construct_absence | merged | P2 | Same forbidden-token question as r003 (coach.claude_md.no_bypass_advertising); smoke varia |
| test_e022_unit_001_claude_md_contains_no_atdd_skip_references.py | policy/forbidden_construct_absence | merged | P2 | Duplicate of r003_unit_001 (no ATDD_SKIP token in CLAUDE.md); should collapse to one polic |
| test_e022_unit_002_claude_md_references_operator_emergency_bypass_doc.py | presence/required_field_presence | direct | P1 | Requires a mandatory pointer to be present in the rendered template; required_field_presen |
| test_e022_unit_003_upgrade_banner_does_not_suggest_force.py | policy/forbidden_construct_absence | direct | P2 | Forbids advertising the destructive --force path in generated banner text; forbidden-const |
| test_e023_smoke_001_live_claude_md_line_count_within_budget.py | sizing/cardinality_bounds | merged | P1 | Same line-count bound as r002 (coach.claude_md.size_budget); smoke variant collapses into  |
| test_e023_unit_001_claude_md_is_at_most_250_lines.py | sizing/cardinality_bounds | merged | P1 | Duplicate of r002_unit_001 (CLAUDE.md <=250 lines); should collapse to one cardinality_bou |
| test_e023_unit_002_claude_md_retains_atdd_lifecycle_and_command_pointers.py | presence/required_field_presence | direct | P1 | Requires the mandatory lifecycle/command-pointer sections to be present after trim; requir |
| test_e024_smoke_001_live_operator_emergency_bypass_doc_present_and_correct.py | non_convention | not_convention_graph | P2 | Documentation-artifact presence/content check, not convention graph. |
| test_e024_unit_001_operator_emergency_bypass_doc_exists.py | non_convention | not_convention_graph | P2 | Documentation-artifact existence check, not convention graph. |
| test_e024_unit_002_operator_emergency_bypass_doc_documents_cli_not_env_var.py | non_convention | not_convention_graph | P2 | Documentation-content check, not convention graph. |
| test_e026_bypass_inventory_guard.py | policy/forbidden_construct_absence | direct | P2 | Meta-guard forbidding new bypass flags above the audited baseline; forbidden-construct-abs |
| test_e032_smoke_001_live_freedom_layer_passes_flipped_validator.py | policy/forbidden_construct_absence | merged | P2 | Live smoke of the same freedom-layer forbidden-command question as e032_unit_001; collapse |
| test_e032_unit_001_validator_rejects_forbidden_command_in_allowlist.py | policy/forbidden_construct_absence | direct | P2 | Forbids a forbidden_bash command appearing in allowed_bash on freedom_layer convention dat |
| test_e032_unit_002_validator_rejects_unscoped_bash_entry.py | grammar/identifier_grammar_conformance | direct | P0 | Allow-list entries must conform to the Bash(cmd:*) scoping grammar; identifier_grammar_con |
| test_e032_unit_003_validator_is_language_agnostic_data_only.py | non_convention | not_convention_graph | P2 | Asserts a property of the validator implementation (data-only), not a convention-graph que |
| test_e036_unit_003_shared_core_bare_baseline.py | non_convention | not_convention_graph | P2 | Git core.bare baseline regression; runtime hermeticity, not convention graph. |
| test_e056_smoke_001_real_gate_scopes_to_current_pr.py | non_convention | not_convention_graph | P2 | PR-scoping behavior driven by live CI env (GITHUB_REF); runtime governance, not convention |
| test_e056_unit_001_pre_smoke_gate_pr_scope.py | non_convention | not_convention_graph | P2 | PR-scope gate logic over live PR set; runtime governance, not convention graph. |
| test_enrich_wagon_registry.py | non_convention | not_convention_graph | P2 | Registry-enrichment migration tooling (SPEC-COACH-UTILS-0290), not convention-graph enforc |
| test_fix_hint_completeness.py | presence/required_field_presence | direct | P1 | Every rule node must carry a fix_hint field; required_field_presence over the convention g |
| test_github_client_mock_spec.py | non_convention | not_convention_graph | P2 | Test-double hygiene over Python source; not a convention-graph question. |
| test_hook_version_gate_honest_message.py | non_convention | not_convention_graph | P2 | Git-hook message content; runtime tooling, not convention graph. |
| test_init_substrate_mode.py | non_convention | not_convention_graph | P2 | CLI init behavior, not convention graph. |
| test_init_themes_prompt.py | non_convention | not_convention_graph | P2 | CLI init prompt behavior, not convention graph. |
| test_issue_advancement.py | non_convention | not_convention_graph | P2 | Post-merge GitHub issue lifecycle behavior; runtime governance, not convention graph. |
| test_issue_gate_completion.py | non_convention | not_convention_graph | P2 | Issue gate-completion governance over live issues, not convention graph. |
| test_issue_validation.py | non_convention | not_convention_graph | P2 | Validates live GitHub Issues / Project v2 fields; runtime governance, not convention graph |
| test_l003_smoke_001_dispatched_agent_bash_log_contains_no_atdd_skip_invocations.py | non_convention | not_convention_graph | P2 | Inspects a live runtime bash log, not a convention-graph artifact. |
| test_m002_smoke_001_live_observer_rules_pass_validator.py | non_convention | not_convention_graph | P2 | Observer-rules runtime spawn contract, not convention graph. |
| test_m002_unit_spawn_non_interactive_validator.py | non_convention | not_convention_graph | P2 | AST/runtime check over spawn code shape, not convention graph. |
| test_manifest_write_discipline.py | non_convention | not_convention_graph | P2 | Manifest-write tooling discipline, not convention-graph enforcement. |
| test_no_hardcoded_rule_severity.py | binding/declaration_to_implementation_binding | direct | P0 | Enforces that severity is derived from the rule binding, not hardcoded; declaration_to_imp |
| test_no_red_phase_tests_in_consumer_entry_points.py | non_convention | not_convention_graph | P2 | Test-collection layout policy (pytest reachability), runtime test shape, not convention gr |
| test_no_stale_suppressions.py | policy/forbidden_construct_absence | direct | P2 | Forbids stale rule-suppression constructs; forbidden-construct-absence over the rule graph |
| test_observer_universal_cospawn.py | non_convention | not_convention_graph | P2 | Runtime spawn/surface substrate behavior, not convention graph. |
| test_open_issue_compliance.py | non_convention | not_convention_graph | P2 | Walks live open issues for compliance; runtime governance, not convention graph. |
| test_phase_machine_init_pre_commit_gate.py | presence/required_field_presence | direct | P1 | Requires the INIT.pre_commit_gate field to be present on the phase_machine convention node |
| test_pr_base_branch.py | non_convention | not_convention_graph | P2 | Evaluates live GitHub PR base branch; runtime governance, not convention graph. |
| test_pr_closes_keyword_discipline.py | non_convention | not_convention_graph | P2 | Evaluates live PR body conventions; runtime governance, not convention graph. |
| test_pr_mass_delete_guard.py | non_convention | not_convention_graph | P2 | Evaluates live PR diff size; runtime governance, not convention graph. |
| test_pr_merge_blocks_pre_smoke_close.py | non_convention | not_convention_graph | P2 | Evaluates live PR/issue phase state; runtime governance, not convention graph. |
| test_pr_phase_alignment.py | non_convention | not_convention_graph | P2 | Evaluates live PR/issue phase alignment; runtime governance, not convention graph. |
| test_pytest_invocation_form.py | non_convention | not_convention_graph | P2 | Pytest subprocess invocation shape; runtime tooling, not convention graph. |
| test_r002_smoke_001_atdd_validate_coach_includes_size_budget_rule.py | sizing/cardinality_bounds | merged | P1 | Live smoke of the CLAUDE.md line-budget bound; same question as r002_unit_001 / e023; coll |
| test_r002_unit_001_validator_fails_when_claude_md_exceeds_budget.py | sizing/cardinality_bounds | direct | P1 | Canonical CLAUDE.md <=250-line cardinality bound (coach.claude_md.size_budget); the target |
| test_r002_unit_002_validator_passes_when_claude_md_within_budget.py | sizing/cardinality_bounds | merged | P1 | Pass-case of the same size_budget cardinality bound; collapses into the one sizing target. |
| test_r003_smoke_001_atdd_validate_coach_includes_no_bypass_advertising_rule.py | policy/forbidden_construct_absence | merged | P2 | Live smoke of the no-bypass-token question; same as r003_unit_001 / e022; collapses into o |
| test_r003_unit_001_validator_fails_when_claude_md_contains_atdd_skip_token.py | policy/forbidden_construct_absence | direct | P2 | Canonical no-ATDD_SKIP-token forbidden-construct rule (coach.claude_md.no_bypass_advertisi |
| test_r003_unit_002_validator_passes_when_claude_md_is_clean.py | policy/forbidden_construct_absence | merged | P2 | Pass-case of the same no-bypass-token rule; collapses into the one policy target. |
| test_readonly_commands_no_writes.py | non_convention | not_convention_graph | P2 | CLI runtime side-effect behavior, not convention graph. |
| test_registry.py | non_convention | not_convention_graph | P2 | Unit test of registry infrastructure, not a convention-graph question. |
| test_release_versioning.py | non_convention | not_convention_graph | P2 | Release/version-bump governance, not convention graph. |
| test_required_label_set.py | non_convention | not_convention_graph | P2 | Required-label coverage over live GitHub issues; runtime governance, not convention graph. |
| test_review_gate_ci_safe.py | non_convention | not_convention_graph | P2 | CI workflow lint, not convention graph. |
| test_rule_disposition_required.py | presence/required_field_presence | direct | P1 | Every rule node must carry a disposition field; required_field_presence over the conventio |
| test_rule_id_registry_coherence.py | coherence/resolved_fact_agreement | direct | P1 | Registry must agree with the set of declared rules; resolved_fact_agreement between regist |
| test_rule_id_uniqueness.py | uniqueness/scoped_identifier_uniqueness | direct | P0 | Canonical rule ids must be unique across the convention graph; scoped_identifier_uniquenes |
| test_rule_validator_binding.py | binding/declaration_to_implementation_binding | direct | P0 | Canonical bidirectional rule<->validator binding archetype; the broad validator that super |
| test_session_naming.py | non_convention | not_convention_graph | P2 | Subject is runtime session names + filesystem layout, not convention-graph identifiers; ad |
| test_spawn_non_interactive_validator.py | non_convention | not_convention_graph | P2 | AST/runtime spawn-shape check, not convention graph. |
| test_sync_theme_block.py | non_convention | not_convention_graph | P2 | CLI sync rendering behavior, not convention graph. |
| test_theme_scanner.py | non_convention | not_convention_graph | P2 | Theme-discovery scanning tooling, not convention graph. |
| test_toolkit_source_layout_assumptions.py | non_convention | not_convention_graph | P2 | Toolkit packaging/layout assumptions over Python source, not convention graph. |
| test_traceability.py | coherence/resolved_fact_agreement | direct | P1 | Contract and telemetry traceability facts must reconcile/agree; resolved_fact_agreement. |
| test_train_registry.py | coverage/source_has_required_target | direct | P1 | Every referenced train must have a registry entry; source_has_required_target over the tra |
| test_unlabeled_open_issues.py | non_convention | not_convention_graph | P2 | Label coverage over live GitHub issues; runtime governance, not convention graph. |
| test_update_feature_paths.py | non_convention | not_convention_graph | P2 | Feature-manifest migration tooling (SPEC-COACH-UTILS-0291), not convention-graph enforceme |
| test_urn_traceability.py | resolution/reference_chain_resolution | direct | P0 | URN references must resolve through their full traceability chain; reference_chain_resolut |
| test_validate_contract_consumers.py | resolution/artifact_reference_resolution | direct | P0 | A manifest's contract-consumer reference must resolve against the contract schema artifact |
| test_validate_uses_live_source_in_checkout.py | non_convention | not_convention_graph | P2 | TestRunner live-source resolution behavior; runtime tooling, not convention graph. |
| test_validator_test_isolation.py | non_convention | not_convention_graph | P2 | Test-isolation regression gate; test hygiene, not convention graph. |
| test_wagonless_graph_context_compliance.py | non_convention | not_convention_graph | P2 | Cross-module check of CLI Graph Context output formatting; runtime tooling, not convention |
| test_wheel_completeness.py | coverage/source_has_required_target | direct | P1 | Every required fixture must be shipped in the wheel; source_has_required_target (packaging |
| test_workflow_consistency.py | non_convention | not_convention_graph | P2 | Consistency over guidance markdown docs; documentation hygiene, not convention graph. |
| test_workflow_template_command_drift.py | non_convention | not_convention_graph | P2 | CLI command parseability/drift between templates and live argparse; runtime/CLI shape, not |
| test_worktree_enforcement.py | non_convention | not_convention_graph | P2 | Git worktree hook-template behavior; runtime tooling, not convention graph. |
| test_y003_smoke_001_guard_catches_polluter.py | non_convention | not_convention_graph | P2 | Git core.bare hermeticity guard smoke; runtime tooling, not convention graph. |
| test_y003_unit_001_repo_root_bare_guard.py | non_convention | not_convention_graph | P2 | Git core.bare/workspace hermeticity guard; runtime tooling, not convention graph. |

**Excluded helpers:**

- `src/atdd/coach/validators/__init__.py` — package marker, not an executable validator
- `src/atdd/coach/validators/conftest.py` — pytest support/fixtures file, not an executable validator
- `src/atdd/coach/validators/_core_bare_baseline.py` — leading-underscore shared helper: poisoned core.bare baseline fixture data reused by validators
- `src/atdd/coach/validators/_violation.py` — leading-underscore shared helper: Violation dataclass used by validators
- `src/atdd/coach/validators/claude_md_validators.py` — non-test_ helper module: CLAUDE.md validator functions imported by the test_e0xx/r0xx entries
- `src/atdd/coach/validators/freedom_layer_validator.py` — non-test_ helper module: freedom-layer (E032) validator implementation imported by the test_e032 entries
- `src/atdd/coach/validators/launch_prompt_wagon_graph_guard.py` — non-test_ helper module: launch-prompt wagon-graph guard implementation
- `src/atdd/coach/validators/red_phase_leak_scanner.py` — non-test_ helper module: RED-phase leak scanner implementation imported by the regression entry
- `src/atdd/coach/validators/rule_id_emission_extractor.py` — non-test_ helper module: AST extractor for emitted rule-ids, imported by binding validators
- `src/atdd/coach/validators/shared_fixtures.py` — non-test_ helper module: shared pytest fixtures for validator tests

## Decommission implications (per persona)

### planner
- replaceable by a convention validant (direct/merged/split/superseded): **25**
- move to extension/workspace later (extension_candidate): **0**
- not convention-graph (keep as persona validator): **6**
- needs a design decision (needs_design): **0**

### tester
- replaceable by a convention validant (direct/merged/split/superseded): **35**
- move to extension/workspace later (extension_candidate): **6**
- not convention-graph (keep as persona validator): **3**
- needs a design decision (needs_design): **0**

### coder
- replaceable by a convention validant (direct/merged/split/superseded): **46**
- move to extension/workspace later (extension_candidate): **3**
- not convention-graph (keep as persona validator): **1**
- needs a design decision (needs_design): **0**

### coach
- replaceable by a convention validant (direct/merged/split/superseded): **36**
- move to extension/workspace later (extension_candidate): **0**
- not convention-graph (keep as persona validator): **76**
- needs a design decision (needs_design): **0**

## P0 variants the implementation issue (#1206) must build

- `src/atdd/validators/conventions/binding/test_commit-trailers-rule-binding.py` ← src/atdd/coach/validators/test_commit_trailers_binding.py
- `src/atdd/validators/conventions/binding/test_no-hardcoded-rule-severity.py` ← src/atdd/coach/validators/test_no_hardcoded_rule_severity.py
- `src/atdd/validators/conventions/binding/test_rule-validator-binding.py` ← src/atdd/coach/validators/test_rule_validator_binding.py
- `src/atdd/validators/conventions/binding/test_runtime-artifacts-rule-binding.py` ← src/atdd/coach/validators/test_e009_unit_001_convention_declares_runtime_artifacts_rule.py
- `src/atdd/validators/conventions/binding/test_spawn-cli-rule-binding.py` ← src/atdd/coach/validators/test_e001_unit_001_spawn_cli_launches_session.py
- `src/atdd/validators/conventions/binding/test_validator-binding-bidirectional.py` ← src/atdd/tester/validators/test_repo_validator_binding.py
- `src/atdd/validators/conventions/binding/test_wmbt-smoke-acceptance-rule-registered.py` ← src/atdd/planner/validators/test_wmbt_smoke_acceptance_rule_registered.py
- `src/atdd/validators/conventions/composition/test_package-data-ships-convention-nodes.py` ← src/atdd/coach/validators/test_composition_data_shipped.py
- `src/atdd/validators/conventions/grammar/test_acceptance-urn-grammar.py` ← src/atdd/tester/validators/test_acceptance_urn_separator.py
- `src/atdd/validators/conventions/grammar/test_artifact-naming-grammar.py` ← src/atdd/tester/validators/test_artifact_naming_category.py
- `src/atdd/validators/conventions/grammar/test_contracts-path-grammar.py` ← src/atdd/tester/validators/test_contracts_structure.py
- `src/atdd/validators/conventions/grammar/test_freedom-layer-bash-scope-grammar.py` ← src/atdd/coach/validators/test_e032_unit_002_validator_rejects_unscoped_bash_entry.py
- `src/atdd/validators/conventions/grammar/test_init-file-urn-grammar.py` ← src/atdd/coder/validators/test_init_file_urns.py
- `src/atdd/validators/conventions/grammar/test_python-test-naming.py` ← src/atdd/tester/validators/test_python_test_naming.py
- `src/atdd/validators/conventions/grammar/test_telemetry-naming-grammar.py` ← src/atdd/tester/validators/test_telemetry_structure.py
- `src/atdd/validators/conventions/grammar/test_theme-must-be-canonical.py` ← src/atdd/planner/validators/test_theme_must_be_canonical.py
- `src/atdd/validators/conventions/grammar/test_train-urn-grammar.py` ← src/atdd/coder/validators/test_train_urns.py
- `src/atdd/validators/conventions/grammar/test_typescript-test-naming.py` ← src/atdd/tester/validators/test_typescript_test_naming.py
- `src/atdd/validators/conventions/grammar/test_urn-header-spec-v3.py` ← src/atdd/tester/validators/test_urn_spec_v3.py
- `src/atdd/validators/conventions/grammar/test_wmbt-vocabulary.py` ← src/atdd/planner/validators/test_wmbt_vocabulary.py
- `src/atdd/validators/conventions/resolution/test_contract-consumer-resolution.py` ← src/atdd/coach/validators/test_validate_contract_consumers.py
- `src/atdd/validators/conventions/resolution/test_draft-wagon-registry.py` ← src/atdd/planner/validators/test_draft_wagon_registry.py
- `src/atdd/validators/conventions/resolution/test_metric-implementation-resolves.py` ← src/atdd/tester/validators/test_metric_implementation.py
- `src/atdd/validators/conventions/resolution/test_plan-cross-refs.py` ← src/atdd/planner/validators/test_plan_cross_refs.py
- `src/atdd/validators/conventions/resolution/test_plan-urn-resolution.py` ← src/atdd/planner/validators/test_plan_urn_resolution.py
- `src/atdd/validators/conventions/resolution/test_route-train-wagon-chain.py` ← src/atdd/coder/validators/test_route_train_wagon_coverage.py
- `src/atdd/validators/conventions/resolution/test_security-ref-resolution.py` ← src/atdd/tester/validators/test_security_ref_binding.py
- `src/atdd/validators/conventions/resolution/test_train-validation.py` ← src/atdd/planner/validators/test_train_validation.py
- `src/atdd/validators/conventions/resolution/test_urn-traceability.py` ← src/atdd/coach/validators/test_urn_traceability.py
- `src/atdd/validators/conventions/resolution/test_wagon-urn-chain.py` ← src/atdd/planner/validators/test_wagon_urn_chain.py
- `src/atdd/validators/conventions/schema/test_contract-schema-conformance.py` ← src/atdd/tester/validators/test_contract_schema_compliance.py
- `src/atdd/validators/conventions/schema/test_dispatch-map-is-registry.py` ← src/atdd/planner/validators/test_dispatch_registry.py
- `src/atdd/validators/conventions/schema/test_plan-wagons.py` ← src/atdd/planner/validators/test_plan_wagons.py
- `src/atdd/validators/conventions/schema/test_train-yaml-render-metadata.py` ← src/atdd/coder/validators/test_train_yaml_render_metadata.py
- `src/atdd/validators/conventions/uniqueness/test_plan-uniqueness.py` ← src/atdd/planner/validators/test_plan_uniqueness.py
- `src/atdd/validators/conventions/uniqueness/test_rule-id-uniqueness.py` ← src/atdd/coach/validators/test_rule_id_uniqueness.py
