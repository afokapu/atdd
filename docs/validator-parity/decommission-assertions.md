# Assertion-accurate decommission readiness (#1207) — READ-ONLY

Legacy candidate files: 109 | variant-covered nodeids: 28 | catch_matrix oracle nodeids: 12

## FILE-READY (every assertion covered or unbound — deletable)  (24)

- src/atdd/coach/validators/test_commit_trailers_binding.py  file_ready=True
    [✓] test_commit_trailers_rule_family_emits_each_required_trailer_id -> binding/commit_trailers_rule_binding  rules=['coach.commit-trailers.phase-required', 'coach.commit-trailers.wmbt-urn-required', 'coach.commit-trailers.agent-id-required', 'coach.commit-trailers.issue-required']

- src/atdd/coach/validators/test_composition_data_shipped.py  file_ready=True
    [✓] test_package_data_ships_core_nodes_and_schema -> composition/package_data_ships_convention_nodes
    [·] test_installed_core_node_ids_resolves_package_relative

- src/atdd/coach/validators/test_e001_unit_001_spawn_cli_launches_session.py  file_ready=True
    [·] test_spawn_module_committed
    [·] test_spawn_module_exposes_required_callables
    [✓] test_spawn_emits_agent_spawned_event_conforming_to_schema -> binding/spawn_cli_rule_binding  rules=['coach.spawn.atdd-spawn-cli']
    [·] test_spawn_adapter_registry_ships_claude_code

- src/atdd/coach/validators/test_e009_unit_001_convention_declares_runtime_artifacts_rule.py  file_ready=True
    [·] test_convention_file_has_rule
    [✓] test_bind_rule_resolves -> binding/runtime_artifacts_rule_binding
    [·] test_disposition_is_strict
    [·] test_fix_hint_names_runtime_path
    [·] test_rules_show_exits_zero

- src/atdd/coach/validators/test_e026_bypass_inventory_guard.py  file_ready=True
    [·] test_count_bypass_flags_function_exists
    [✓] test_current_hook_bypass_count_at_baseline -> policy/bypass_inventory
    [·] test_synthetic_excess_count_triggers_guard
    [·] test_advisory_flags_not_counted
    [·] test_ci_only_flags_not_counted

- src/atdd/coach/validators/test_e032_smoke_001_live_freedom_layer_passes_flipped_validator.py  file_ready=True
    [✓] test_live_freedom_layer_passes_flipped_validator -> policy/freedom_layer_bash_scope
    [✓] test_every_live_allowed_bash_entry_is_scoped -> grammar/freedom_layer_bash_scope_grammar

- src/atdd/coach/validators/test_fix_hint_completeness.py  file_ready=True
    [✓] test_every_fix_hint_satisfies_completeness_contract -> presence/rule_has_fix_hint  rules=['coach.rule-id.fix-hint-completeness']

- src/atdd/coach/validators/test_no_hardcoded_rule_severity.py  file_ready=True
    [✓] test_no_hardcoded_rule_severity_in_migrated_validators -> binding/no_hardcoded_rule_severity  rules=['coach.rule-id.no-hardcoded-rule-severity']

- src/atdd/coach/validators/test_no_stale_suppressions.py  file_ready=True
    [✓] test_no_stale_suppressions -> policy/no_stale_suppressions  rules=['coach.rule-id.stale-suppression']

- src/atdd/coach/validators/test_phase_machine_init_pre_commit_gate.py  file_ready=True
    [·] test_phase_machine_init_has_pre_commit_gate_field
    [✓] test_phase_machine_init_pre_commit_gate_invokes_validate_planner -> presence/phase_machine_init_precommit_gate
    [·] test_installed_phase_machine_convention_ships_init_pre_commit_gate

- src/atdd/coach/validators/test_rule_disposition_required.py  file_ready=True
    [✓] test_rule_disposition_required -> presence/rule_has_disposition  rules=['coach.rule-id.disposition-required']

- src/atdd/planner/validators/test_draft_wagon_registry.py  file_ready=True
    [·] test_draft_wagons_are_valid_yaml
    [·] test_draft_wagons_not_duplicated_in_manifests
    [·] test_registry_produce_artifacts_follow_convention
    [✓] test_registry_consume_references_valid_wagons -> resolution/draft_wagon_registry
    [·] test_registry_produce_artifacts_have_consumers
    [·] test_draft_wagon_contract_coherence
    [·] test_registry_wagon_slugs_are_unique
    [·] test_registry_has_all_implemented_wagons
    [·] test_registry_implemented_wagons_have_path_and_manifest

- src/atdd/planner/validators/test_feedback_loop_smoke_closes_the_loop.py  file_ready=True
    [✓] test_every_feedback_loop_feature_has_close_the_loop_smoke -> presence/feedback_loop_close_the_loop

- src/atdd/planner/validators/test_hierarchy_coverage.py  file_ready=True
    [·] test_all_wagons_in_at_least_one_train
    [·] test_all_train_wagon_refs_exist
    [·] test_all_features_in_wagon_manifest
    [·] test_all_wagon_feature_refs_exist
    [·] test_all_wmbts_in_at_least_one_feature
    [✓] test_all_wmbts_have_acceptances -> coverage/hierarchy_coverage  rules=['planner.coverage.every-wmbt-must-have']
    [·] test_planner_coverage_summary

- src/atdd/planner/validators/test_no_cross_wagon_consume_cycle.py  file_ready=True
    [✓] test_no_cross_wagon_consume_cycle -> acyclicity/_parity  rules=['planner.wagon.no-consume-cycle']
    [·] test_validator_detects_synthetic_cycle
    [·] test_validator_passes_on_acyclic_chain

- src/atdd/planner/validators/test_no_orphan_nodes.py  file_ready=True
    [✓] test_no_orphan_convention_nodes -> coverage/no_orphan_nodes  rules=['planner.relationship.no-orphan-nodes']

- src/atdd/planner/validators/test_plan_urn_resolution.py  file_ready=True  ⚠ catch_matrix oracle: test_contract_urn_resolves_to_directory
    [✓] test_contract_urn_resolves_to_directory -> resolution/plan_urn_resolution
    [·] test_telemetry_urn_resolves_to_directory
    [·] test_telemetry_directory_contains_signal_files
    [·] test_all_contract_urns_are_unique
    [·] test_all_telemetry_urns_are_unique
    [·] test_contracts_directory_structure_matches_urns
    [·] test_telemetry_directory_structure_matches_urns

- src/atdd/planner/validators/test_smoke_synthetic_fixture_bypass.py  file_ready=True
    [✓] test_no_smoke_tests_use_synthetic_fixtures -> policy/smoke_synthetic_fixture_bypass

- src/atdd/planner/validators/test_theme_archetype_alignment.py  file_ready=True
    [✓] test_archetype_themes_align_with_source_roots -> coherence/theme_archetype_alignment
    [·] test_scanner_surfaces_existing_themes
    [·] test_aligned_archetype_theme_passes

- src/atdd/planner/validators/test_theme_commons_coach_boundary.py  file_ready=True
    [✓] test_commons_wagons_do_not_import_coach -> boundary/_parity  rules=['planner.theme.commons-coach-boundary']
    [·] test_commons_wagon_importing_coach_is_flagged
    [·] test_coach_themed_wagon_may_import_coach

- src/atdd/planner/validators/test_theme_zero_mandatory.py  file_ready=True
    [✓] test_commons_is_always_in_resolved_theme_set -> presence/theme_zero_mandatory  rules=['planner.theme.theme-zero-mandatory']
    [·] test_override_cannot_remove_commons_floor
    [·] test_defaults_contain_commons_floor

- src/atdd/planner/validators/test_train_family_matches_terminal_contract.py  file_ready=True
    [·] test_check_flags_behavior_with_commit_receipt_terminal
    [·] test_check_flags_delivery_without_commit_receipt_terminal
    [·] test_check_passes_delivery_with_commit_receipt
    [·] test_check_passes_behavior_without_commit_receipt
    [·] test_check_skips_train_without_family
    [·] test_check_flags_invalid_family
    [✓] test_real_trains_family_matches_terminal_contract -> coherence/train_family_matches_terminal_contract  rules=['planner.train.family-matches-terminal-contract']

- src/atdd/planner/validators/test_wmbt_consistency.py  file_ready=True
    [✓] test_wagon_manifest_wmbt_codes_exist_as_files -> coherence/wmbt_consistency
    [·] test_wmbt_files_declared_in_wagon_manifest
    [·] test_feature_acceptance_criteria_match_wmbt_files
    [·] test_wmbt_file_urns_match_expected_pattern
    [·] test_wmbt_count_matches_actual_files

- src/atdd/planner/validators/test_wmbt_has_smoke_acceptance.py  file_ready=True
    [✓] test_every_wmbt_has_smoke_acceptance -> coverage/wmbt_has_smoke_acceptance  rules=['planner.wmbt.must-have-smoke-acceptance']

## BLOCKED (>=1 migrated-rule assertion with NO covering variant — build variant first)  (29)

- src/atdd/coach/validators/test_rule_validator_binding.py  file_ready=False  ⚠ catch_matrix oracle: test_every_enforced_rule_has_real_validator
    [✗ BLOCKED] test_every_enforced_rule_has_real_validator  rules=['coach.rule-id.validator-binding-violation']

- src/atdd/coach/validators/test_wheel_completeness.py  file_ready=False
    [✗ BLOCKED] test_validator_fixtures_present_in_wheel  rules=['coach.wheel-completeness.fixture-missing-from-wheel']

- src/atdd/coder/validators/test_complexity.py  file_ready=False
    [✗ BLOCKED] test_cyclomatic_complexity_under_threshold  rules=['coder.refactor.complexity-cyclomatic', 'coder.refactor.complexity-nesting', 'coder.refactor.complexity-length', 'coder.refactor.complexity-params', 'coder.refactor.complexity-cognitive']
    [·] test_nesting_depth_under_threshold
    [·] test_function_length_under_threshold
    [·] test_function_parameter_count_under_threshold
    [·] test_cognitive_complexity_under_threshold

- src/atdd/coder/validators/test_complexity_typescript.py  file_ready=False
    [✗ BLOCKED] test_cyclomatic_complexity_typescript  rules=['coder.refactor.complexity-cyclomatic-typescript', 'coder.refactor.complexity-nesting-typescript', 'coder.refactor.complexity-length-typescript']
    [·] test_nesting_depth_typescript
    [·] test_function_length_typescript

- src/atdd/coder/validators/test_composition_completeness.py  file_ready=False
    [✗ BLOCKED] test_composition_convention_exists_and_has_required_sections  rules=['coder.refactor.composition-consumer', 'coder.refactor.composition-root']
    [·] test_existing_conventions_reference_composition_rules
    [·] test_composition_completeness_python_fixture_passes_for_complete_and_partial_features
    [·] test_composition_completeness_python_fixture_detects_missing_setter_call
    [·] test_composition_completeness_typescript_fixture_detects_cameo_and_import_type_gaps
    [·] test_composition_completeness_typescript_fixture_accepts_barrels_and_partial_features
    [·] test_composition_completeness_python_live_repo
    [·] test_composition_completeness_typescript_live_repo
    [·] test_composition_completeness_supabase_live_repo

- src/atdd/coder/validators/test_cross_language_consistency.py  file_ready=False
    [✗ BLOCKED] test_entity_classes_exist_across_languages  rules=['coder.boundaries.xlang-entity', 'coder.boundaries.xlang-enum', 'coder.boundaries.xlang-naming', 'coder.boundaries.xlang-contract']
    [·] test_enums_match_across_languages
    [·] test_naming_conventions_consistent
    [·] test_api_contracts_honored_across_languages

- src/atdd/coder/validators/test_dead_code_python.py  file_ready=False
    [✗ BLOCKED] test_no_unreachable_python_files  rules=['coder.dead-code.reachability']
    [·] test_init_reexports_create_graph_edges
    [·] test_composition_roots_always_reachable
    [·] test_dead_code_convention_exists

- src/atdd/coder/validators/test_dead_code_typescript.py  file_ready=False
    [✗ BLOCKED] test_no_unreachable_typescript_files  rules=['coder.dead-code.reachability-typescript']
    [·] test_barrel_reexports_create_graph_edges
    [·] test_composition_roots_always_reachable
    [·] test_dead_code_convention_exists

- src/atdd/coder/validators/test_hierarchy_coverage.py  file_ready=False
    [✗ BLOCKED] test_all_features_have_implementations  rules=['coder.coverage.every-feature-must-have', 'coder.design.hierarchy-coverage']
    [✗ BLOCKED] test_all_implementations_have_tests  rules=['coder.coverage.every-implementation-must-have']
    [·] test_coder_coverage_summary

- src/atdd/coder/validators/test_quality_metrics.py  file_ready=False
    [✗ BLOCKED] test_maintainability_index_above_threshold  rules=['coder.refactor.quality-mi', 'coder.refactor.quality-comments', 'coder.refactor.quality-duplication', 'coder.refactor.quality-naming', 'coder.refactor.quality-file-length']
    [·] test_adequate_code_comments
    [·] test_no_significant_code_duplication
    [·] test_consistent_naming_conventions
    [·] test_file_line_count

- src/atdd/coder/validators/test_quality_metrics_typescript.py  file_ready=False
    [✗ BLOCKED] test_maintainability_index_typescript  rules=['coder.refactor.quality-mi-typescript', 'coder.refactor.quality-comments-typescript']
    [·] test_comment_ratio_typescript

- src/atdd/coder/validators/test_query_count.py  file_ready=False
    [✗ BLOCKED] test_no_db_calls_inside_loops  rules=['coder.refactor.nplus1']

- src/atdd/planner/validators/test_dispatch_registry.py  file_ready=False
    [✓] test_real_dispatch_registry_is_declared_and_schema_valid -> schema/dispatch_map_is_registry
    [✗ BLOCKED] test_real_dispatch_entries_well_formed  rules=['planner.train.dispatch-map-is-registry', 'planner.train.dispatch-composite-key-exceptional']
    [·] test_simple_key_passes
    [·] test_composite_without_justification_is_flagged
    [·] test_composite_with_justification_passes
    [·] test_multi_field_discriminant_is_flagged
    [·] test_entry_missing_train_id_is_flagged

- src/atdd/planner/validators/test_theme_must_be_canonical.py  file_ready=False  ⚠ catch_matrix oracle: test_every_wagon_theme_is_canonical
    [✗ BLOCKED] test_every_wagon_theme_is_canonical -> tests/test_sentinels  rules=['planner.theme.must-be-canonical']
    [·] test_retired_game_theme_is_flagged
    [·] test_canonical_themes_pass
    [·] test_taxonomy_is_exactly_five

- src/atdd/planner/validators/test_theme_urn_namespace_matches.py  file_ready=False
    [✗ BLOCKED] test_produced_urn_prefix_matches_theme  rules=['planner.theme.urn-namespace-matches']
    [·] test_urn_prefix_mismatch_is_flagged
    [·] test_matching_prefix_passes

- src/atdd/planner/validators/test_train_validation.py  file_ready=False
    [·] test_train_ids_follow_numbering_convention
    [·] test_train_theme_matches_first_digit
    [✗ BLOCKED] test_train_files_exist_for_registry_entries  rules=['planner.train.registry']
    [·] test_all_train_files_registered
    [·] test_train_id_matches_filename
    [·] test_train_wagons_exist
    [·] test_train_dependencies_are_valid
    [·] test_train_artifacts_follow_naming_convention
    [·] test_train_artifacts_exist_in_wagons
    [·] test_registry_themes_are_valid
    [·] test_trains_match_schema
    [·] test_train_path_file_normalization
    [·] test_train_ids_globally_unique
    [·] test_train_theme_derived_from_group_key
    [·] test_train_explicit_theme_matches_group
    [·] test_train_yaml_themes_include_derived
    [·] test_train_participants_canonical_wagon_source
    [·] test_train_registry_wagons_subset_of_yaml
    [·] test_train_primary_wagon_in_participants
    [·] test_train_test_field_typing
    [·] test_train_code_field_typing
    [·] test_train_expectations_structure
    [·] test_train_status_inference
    [·] test_train_status_expectations_conflict
    [·] test_trains_are_linear_no_loops_or_routes
    [·] test_train_sequences_have_sequential_step_numbers
    [·] test_wagons_with_wmbts_must_be_in_a_train
    [·] test_empty_trains_generate_warning
    [✓] test_train_wagon_references_exist_in_manifests -> resolution/train_validation

- src/atdd/planner/validators/test_wagon_coupling_complexity.py  file_ready=False
    [✗ BLOCKED] test_wagon_coupling_complexity_reported  rules=['planner.wagon.coupling-complexity']
    [·] test_compute_coupling_metric

- src/atdd/planner/validators/test_wagon_separability.py  file_ready=False
    [✗ BLOCKED] test_wagon_separability_reported  rules=['planner.wagon.separability']
    [·] test_separability_flags_synthetic_merge

- src/atdd/tester/validators/test_acceptance_disposition.py  file_ready=False
    [✗ BLOCKED] test_no_disposition_in_repo_yaml  rules=['tester.acceptance-violation.disposition-must-not-be-declared']

- src/atdd/tester/validators/test_acceptance_measurable.py  file_ready=False
    [✗ BLOCKED] test_every_acceptance_has_enforcement  rules=['tester.acceptance-violation.acceptance-must-be-measurable']

- src/atdd/tester/validators/test_acceptance_phase.py  file_ready=False
    [✗ BLOCKED] test_every_acceptance_declares_phase  rules=['tester.acceptance-violation.acceptance-must-declare-phase']

- src/atdd/tester/validators/test_hermetic_integration_contract.py  file_ready=False
    [✗ BLOCKED] test_no_undeclared_hermetic_fakes  rules=['tester.acceptance-violation.hermetic-fake-must-declare-contract']

- src/atdd/tester/validators/test_hermetic_live_smoke_pairing.py  file_ready=False
    [✗ BLOCKED] test_hermetic_live_smoke_required_is_paired  rules=['tester.acceptance-violation.hermetic-live-smoke-required-must-have-paired-smoke-acceptance']

- src/atdd/tester/validators/test_hierarchy_coverage.py  file_ready=False
    [·] test_all_acceptances_have_tests
    [·] test_all_contracts_referenced
    [·] test_all_contract_refs_exist
    [·] test_all_telemetry_referenced
    [·] test_all_telemetry_refs_exist
    [✗ BLOCKED] test_telemetry_manifest_complete  rules=['tester.coverage.tracking-manifest-must-be']
    [·] test_tester_coverage_summary

- src/atdd/tester/validators/test_live_smoke_execution.py  file_ready=False
    [✗ BLOCKED] test_every_live_smoke_acceptance_executed  rules=['tester.acceptance-violation.live-smoke-acceptance-must-execute']

- src/atdd/tester/validators/test_metric_implementation.py  file_ready=False
    [✗ BLOCKED] test_every_signal_metric_has_compute_function  rules=['tester.acceptance-violation.metric-implementation-must-exist']

- src/atdd/tester/validators/test_no_polluting_patterns.py  file_ready=False
    [·] test_flags_bare_init_with_getcwd_cwd
    [·] test_flags_bare_init_with_path_cwd
    [·] test_flags_core_bare_no_scoping
    [·] test_flags_core_bare_with_bad_cwd
    [·] test_clean_code_passes_without_violations
    [·] test_scan_text_handles_invalid_syntax_gracefully
    [✗ BLOCKED] test_repo_has_no_pollution_patterns  rules=['tester.test-isolation.no-polluting-patterns']

- src/atdd/tester/validators/test_repo_validator_binding.py  file_ready=False
    [✗ BLOCKED] test_validator_binding_is_bidirectional  rules=['tester.acceptance-violation.validator-binding-must-be-bidirectional']

- src/atdd/tester/validators/test_security_ref_binding.py  file_ready=False
    [·] test_acceptance_ref_resolves_and_passes
    [✗ BLOCKED] test_every_abuse_case_resolves  rules=['tester.acceptance-violation.security-rule-must-have-acceptance-ref-resolved']

## UNBOUND-ONLY (no rule bindings; structural checks — deletable, record coverage drop)  (56)

- src/atdd/coach/validators/test_d002_unit_004_rule_id_severity_matches_registry.py  file_ready=True
    [·] test_negative_fixture_exists
    [·] test_severity_mismatch_rejected
    [·] test_conforming_rule_id_accepted
    [·] test_null_rule_id_accepted

- src/atdd/coach/validators/test_e022_unit_002_claude_md_references_operator_emergency_bypass_doc.py  file_ready=True
    [·] test_claude_md_references_operator_emergency_bypass_doc

- src/atdd/coach/validators/test_e023_smoke_001_live_claude_md_line_count_within_budget.py  file_ready=True
    [·] test_live_claude_md_line_count_within_budget

- src/atdd/coach/validators/test_e023_unit_001_claude_md_is_at_most_250_lines.py  file_ready=True
    [·] test_claude_md_is_at_most_250_lines

- src/atdd/coach/validators/test_e023_unit_002_claude_md_retains_atdd_lifecycle_and_command_pointers.py  file_ready=True
    [·] test_claude_md_retains_atdd_lifecycle_and_command_pointers

- src/atdd/coach/validators/test_r002_smoke_001_atdd_validate_coach_includes_size_budget_rule.py  file_ready=True
    [·] test_atdd_validate_coach_includes_size_budget_rule

- src/atdd/coach/validators/test_r002_unit_001_validator_fails_when_claude_md_exceeds_budget.py  file_ready=True
    [·] test_size_budget_validator_fails_for_oversized_file
    [·] test_size_budget_validator_error_message_references_count_and_budget

- src/atdd/coach/validators/test_r002_unit_002_validator_passes_when_claude_md_within_budget.py  file_ready=True
    [·] test_size_budget_validator_passes_for_exactly_250_lines
    [·] test_size_budget_validator_passes_for_250_minus_one_lines

- src/atdd/coach/validators/test_rule_id_registry_coherence.py  file_ready=True
    [·] test_rule_id_registry_coherence

- src/atdd/coach/validators/test_rule_id_uniqueness.py  file_ready=True
    [·] test_rule_id_grammar_and_required_fields
    [·] test_rule_id_uniqueness
    [·] test_superseded_by_targets_exist

- src/atdd/coach/validators/test_traceability.py  file_ready=True
    [·] test_detect_missing_contract_references
    [·] test_reconcile_contract_urn_variations
    [·] test_propose_and_apply_contract_fix
    [·] test_validate_bidirectional_traceability
    [·] test_detect_mismatched_producer
    [·] test_batch_reconciliation_report
    [·] test_detect_missing_telemetry_references
    [·] test_leverage_existing_test_diagnostics
    [·] test_clean_architecture_layers

- src/atdd/coach/validators/test_train_registry.py  file_ready=True
    [·] test_inventory_reports_train_gaps
    [·] test_gap_report_format_validation
    [·] test_gap_counts_match_arrays
    [·] test_gap_train_ids_are_valid

- src/atdd/coach/validators/test_urn_traceability.py  file_ready=True
    [·] test_no_orphaned_contracts
    [·] test_no_broken_contract_urns
    [·] test_urn_resolution_deterministic
    [·] test_traceability_edges_complete
    [·] test_wagon_produces_contracts
    [·] test_no_broken_telemetry_urns
    [·] test_train_wagon_references_valid
    [·] test_urn_patterns_valid
    [·] test_feature_chain_completeness
    [·] test_no_orphaned_components
    [·] test_component_wagon_ancestry_valid
    [·] test_full_traceability_validation

- src/atdd/coach/validators/test_validate_contract_consumers.py  file_ready=True
    [·] test_detect_consumer_mismatches
    [·] test_apply_consumer_sync_updates

- src/atdd/coder/validators/test_frontend_composition_root.py  file_ready=True
    [·] test_frontend_composition_root_matches_contract
    [·] test_extract_class_members_positive
    [·] test_extract_class_members_renamed_class_returns_empty
    [·] test_analyze_composition_root_reports_missing_methods
    [·] test_analyze_composition_root_passes_when_contract_satisfied
    [·] test_analyze_composition_root_reports_missing_file

- src/atdd/coder/validators/test_god_hook_elimination.py  file_ready=True
    [·] test_god_hooks_must_be_allowlisted
    [·] test_god_hook_allowlist_entries_have_migration

- src/atdd/coder/validators/test_green_cross_stack_layers.py  file_ready=True
    [·] test_all_stacks_use_same_layer_names
    [·] test_no_alternative_layer_names
    [·] test_layer_names_lowercase

- src/atdd/coder/validators/test_green_layer_dependencies.py  file_ready=True
    [·] test_domain_has_no_layer_imports
    [·] test_application_only_imports_domain
    [·] test_integration_only_imports_domain
    [·] test_presentation_imports_valid

- src/atdd/coder/validators/test_green_python_layer_structure.py  file_ready=True
    [·] test_green_enforces_python_layers
    [·] test_python_component_layer_mapping

- src/atdd/coder/validators/test_green_supabase_layer_structure.py  file_ready=True
    [·] test_green_enforces_supabase_layers
    [·] test_supabase_index_is_thin

- src/atdd/coder/validators/test_init_file_urns.py  file_ready=True
    [·] test_python_init_files_have_urns
    [·] test_dart_index_files_have_urns
    [·] test_typescript_index_files_have_urns
    [·] test_urn_generation_logic

- src/atdd/coder/validators/test_presentation_ratchet_requires_smoke.py  file_ready=True
    [·] test_detects_25pct_reduction_in_presentation_tsx
    [·] test_full_deletion_treated_as_100pct_reduction
    [·] test_ignores_reductions_at_or_below_threshold
    [·] test_ignores_files_outside_presentation_layer
    [·] test_ignores_growth_and_unchanged_files
    [·] test_ignores_zero_before_lines
    [·] test_python_supabase_presentation_files_in_scope
    [·] test_default_globs_match_documented_extensions
    [·] test_smoke_evidence_path_uses_dotatdd_directory
    [·] test_smoke_evidence_dir_under_dotatdd
    [·] test_has_smoke_evidence_false_when_missing
    [·] test_has_smoke_evidence_true_when_recorded
    [·] test_record_smoke_evidence_persists_metadata
    [·] test_rule_id_and_severity_are_documented_constants
    [·] test_violation_emitted_when_evidence_missing
    [·] test_no_violation_when_evidence_present
    [·] test_no_violation_when_no_reductions
    [·] test_collect_repo_reductions_detects_presentation_trim
    [·] test_collect_repo_reductions_handles_full_deletion
    [·] test_collect_repo_reductions_ignores_non_presentation
    [·] test_presentation_ratchet_requires_smoke

- src/atdd/coder/validators/test_route_train_wagon_coverage.py  file_ready=True
    [·] test_unregistered_train_id_fails
    [·] test_unregistered_wagon_in_train_fails
    [·] test_dynamic_train_id_warns
    [·] test_resolved_chain_passes
    [·] test_route_train_wagon_coverage
    [·] test_route_train_wagon_allowlist_hygiene

- src/atdd/coder/validators/test_station_master_pattern.py  file_ready=True
    [·] test_composition_accepts_shared_dependencies
    [·] test_direct_adapters_exist_for_cross_wagon_clients
    [·] test_game_py_delegates_to_composition

- src/atdd/coder/validators/test_train_infrastructure.py  file_ready=True
    [·] test_trains_directory_exists
    [·] test_train_infrastructure_files_exist
    [·] test_train_runner_class_exists
    [·] test_train_models_exist
    [·] test_wagons_implement_run_train
    [·] test_game_py_imports_train_runner
    [·] test_game_py_has_journey_map
    [·] test_game_py_has_train_execution_endpoint
    [·] test_e2e_conftest_uses_production_train_runner
    [·] test_contract_validator_is_real
    [·] test_e2e_conftest_uses_real_contract_validator
    [·] test_train_convention_exists
    [·] test_train_convention_documents_key_patterns
    [·] test_no_wagon_to_wagon_imports
    [·] test_backend_runner_paths
    [·] test_frontend_code_allowed_roots
    [·] test_fastapi_template_enforcement

- src/atdd/coder/validators/test_train_urns.py  file_ready=True
    [·] test_theme_orchestrators_exist
    [·] test_theme_orchestrators_have_train_urns
    [·] test_train_urns_match_convention_format
    [·] test_train_urns_reference_existing_specs
    [·] test_train_specs_have_implementations
    [·] test_train_convention_file_exists

- src/atdd/coder/validators/test_train_yaml_render_metadata.py  file_ready=True
    [·] test_train_yaml_render_metadata_matches_schema
    [·] test_validate_train_yaml_passes_for_compliant_file
    [·] test_validate_train_yaml_reports_wrong_auth_required_type
    [·] test_validate_train_yaml_reports_missing_required_field
    [·] test_validate_train_yaml_ignores_empty_file
    [·] test_load_schema_reads_json

- src/atdd/coder/validators/test_wagon_trains_export_shape.py  file_ready=True
    [·] test_wagon_trains_export_shape_matches_contract
    [·] test_extract_exports_finds_const_function_and_list_forms
    [·] test_extract_exports_returns_empty_for_plain_source
    [·] test_analyze_wagon_reports_missing_trains_file
    [·] test_analyze_wagon_reports_partial_exports
    [·] test_analyze_wagon_passes_when_contract_satisfied

- src/atdd/planner/validators/test_plan_cross_refs.py  file_ready=True  ⚠ catch_matrix oracle: test_trains_reference_valid_wagons
    [·] test_wagon_consume_references_valid_produce_or_external
    [·] test_no_circular_dependencies_simple
    [·] test_trains_reference_valid_wagons
    [·] test_produce_and_consume_artifact_names_are_coherent
    [·] test_wagon_to_field_references_valid_destinations

- src/atdd/planner/validators/test_plan_uniqueness.py  file_ready=True  ⚠ catch_matrix oracle: test_wagon_slugs_are_unique, test_train_ids_are_unique, test_produce_artifact_names_unique_per_wagon, test_feature_urns_unique_per_wagon, test_contract_urns_unique_globally
    [·] test_wagon_slugs_are_unique
    [·] test_train_ids_are_unique
    [·] test_produce_artifact_names_unique_per_wagon
    [·] test_wmbt_ids_unique_per_wagon
    [·] test_feature_urns_unique_per_wagon
    [·] test_contract_urns_unique_globally
    [·] test_telemetry_urns_unique_globally

- src/atdd/planner/validators/test_plan_wagons.py  file_ready=True  ⚠ catch_matrix oracle: test_wagon_manifest_matches_schema
    [·] test_wagon_manifest_matches_schema
    [·] test_all_wagons_have_required_fields
    [·] test_all_produce_items_have_contract_and_telemetry
    [·] test_wagon_slugs_match_directory_names
    [·] test_wagon_names_follow_verb_object_pattern
    [·] test_feature_names_follow_verb_object_pattern
    [·] test_produce_artifact_names_follow_convention
    [·] test_contract_urns_match_pattern
    [·] test_telemetry_urns_match_pattern

- src/atdd/planner/validators/test_wagon_urn_chain.py  file_ready=True  ⚠ catch_matrix oracle: test_all_wagons_have_complete_chains
    [·] test_wagon_complete_urn_chain
    [·] test_all_wagons_have_complete_chains

- src/atdd/planner/validators/test_wmbt_vocabulary.py  file_ready=True  ⚠ catch_matrix oracle: test_wmbt_urn_step_code_matches_step_field
    [·] test_wmbt_files_use_authorized_steps
    [·] test_wmbt_files_use_authorized_directions
    [·] test_wmbt_files_use_authorized_dimensions
    [·] test_wmbt_files_use_authorized_lenses
    [·] test_wmbt_files_have_valid_object_of_control
    [·] test_wmbt_statements_follow_construction_pattern
    [·] test_wmbt_urn_step_code_matches_step_field

- src/atdd/tester/validators/test_acceptance_urn_separator.py  file_ready=True
    [·] test_acceptance_urn_format_updated
    [·] test_urn_builder_acceptance_separator
    [·] test_schema_validates_new_urn_format

- src/atdd/tester/validators/test_artifact_naming_category.py  file_ready=True
    [·] test_logical_pattern_has_theme_hierarchy
    [·] test_physical_pattern_has_segments
    [·] test_examples_use_theme_hierarchy
    [·] test_no_legacy_domain_resource_examples
    [·] test_api_pattern_has_theme_segments
    [·] test_api_examples_include_theme_based
    [·] test_urn_pattern_preserves_colons_and_dots
    [·] test_urn_examples_use_theme_hierarchy
    [·] test_contract_id_unversioned
    [·] test_contract_examples_use_theme_hierarchy
    [·] test_wagon_examples_use_maintain_ux
    [·] test_wagon_produces_theme_hierarchy_artifacts
    [·] test_validation_regex_allows_theme_hierarchy
    [·] test_migration_note_documents_refactoring

- src/atdd/tester/validators/test_contract_schema_compliance.py  file_ready=True
    [·] test_contract_schemas_validate_against_meta_schema
    [·] test_contract_versions_follow_semver
    [·] test_contract_references_are_valid
    [·] test_contract_acceptance_references_exist
    [·] test_no_duplicate_contract_ids
    [·] test_contract_id_format_follows_convention
    [·] test_contract_directory_structure_matches_artifact
    [·] test_contract_api_method_inference
    [·] test_contract_traceability_richness

- src/atdd/tester/validators/test_contract_security.py  file_ready=True
    [·] test_secured_operations_have_required_headers
    [·] test_operations_have_explicit_security
    [·] test_secured_operations_have_security_acceptance
    [·] test_error_responses_have_no_sensitive_fields

- src/atdd/tester/validators/test_contracts_structure.py  file_ready=True
    [·] test_contracts_directory_exists
    [·] test_contracts_follow_domain_resource_pattern
    [·] test_contract_directories_contain_files
    [·] test_no_orphaned_contract_directories
    [·] test_contract_files_are_valid_formats
    [·] test_wagon_produce_contracts_exist

- src/atdd/tester/validators/test_coverage_adequacy.py  file_ready=True
    [·] test_all_acceptance_criteria_have_tests
    [·] test_coverage_meets_threshold
    [·] test_no_orphaned_tests

- src/atdd/tester/validators/test_dual_ac_reference.py  file_ready=True
    [·] test_all_tests_have_dual_ac_references
    [·] test_dual_ac_reference_format_examples

- src/atdd/tester/validators/test_fixture_validity.py  file_ready=True
    [·] test_fixtures_match_contract_schemas
    [·] test_fixtures_do_not_contain_production_data
    [·] test_fixtures_use_descriptive_names

- src/atdd/tester/validators/test_migration_coverage.py  file_ready=True
    [·] test_all_contracts_have_migrations
    [·] test_migration_templates_reviewed

- src/atdd/tester/validators/test_python_test_naming.py  file_ready=True
    [·] test_python_test_files_named_correctly
    [·] test_python_test_functions_named_correctly
    [·] test_python_test_classes_named_correctly
    [·] test_python_test_files_have_mandatory_slugs
    [·] test_python_test_files_are_in_correct_locations

- src/atdd/tester/validators/test_red_layer_validation.py  file_ready=True
    [·] test_rejects_non_layered_python_tests
    [·] test_rejects_non_layered_flutter_tests
    [·] test_rejects_non_layered_supabase_tests

- src/atdd/tester/validators/test_red_python_layer_structure.py  file_ready=True
    [·] test_red_defines_python_layer_structure
    [·] test_red_creates_layer_directories

- src/atdd/tester/validators/test_red_supabase_layer_structure.py  file_ready=True
    [·] test_red_defines_supabase_layer_structure
    [·] test_http_tests_in_presentation

- src/atdd/tester/validators/test_smoke_coverage.py  file_ready=True
    [·] test_smoke_tests_have_no_mock_imports
    [·] test_smoke_tests_have_correct_headers
    [·] test_smoke_coverage_gaps

- src/atdd/tester/validators/test_smoke_no_collaborator_substitution.py  file_ready=True
    [·] test_smoke_tests_do_not_substitute_collaborators

- src/atdd/tester/validators/test_telemetry_structure.py  file_ready=True
    [·] test_telemetry_directory_exists
    [·] test_telemetry_follows_theme_domain_pattern
    [·] test_telemetry_signal_files_follow_naming_convention
    [·] test_telemetry_directories_contain_signal_files
    [·] test_metric_signals_have_measure_suffix
    [·] test_event_signals_have_no_measure_suffix
    [·] test_telemetry_signals_validate_against_meta_schema
    [·] test_telemetry_versions_follow_semver
    [·] test_telemetry_contract_references_exist
    [·] test_telemetry_acceptance_references_exist
    [·] test_no_duplicate_telemetry_ids
    [·] test_no_orphaned_telemetry_directories

- src/atdd/tester/validators/test_train_backend_e2e.py  file_ready=True
    [·] test_backend_e2e_path_convention
    [·] test_backend_e2e_pytest_markers
    [·] test_backend_e2e_see_annotation
    [·] test_backend_e2e_runner_evidence

- src/atdd/tester/validators/test_train_completeness.py  file_ready=True
    [·] test_train_completeness

- src/atdd/tester/validators/test_train_e2e_existence.py  file_ready=True
    [·] test_train_e2e_existence

- src/atdd/tester/validators/test_train_route_smoke_coverage.py  file_ready=True
    [·] test_train_route_smoke_coverage
    [·] test_train_route_smoke_no_mocks

- src/atdd/tester/validators/test_typescript_test_naming.py  file_ready=True
    [·] test_typescript_test_files_use_kebab_case
    [·] test_typescript_test_files_match_acceptance_pattern
    [·] test_typescript_test_files_have_urn_comment
    [·] test_typescript_test_files_organized_by_wagon
    [·] test_typescript_test_filename_matches_urn_acceptance_id
    [·] test_typescript_test_files_use_correct_extension

- src/atdd/tester/validators/test_typescript_test_structure.py  file_ready=True
    [·] test_typescript_test_files_have_urn_header
    [·] test_component_tests_use_tsx_extension
    [·] test_preact_test_files_use_urn_filename_format

- src/atdd/tester/validators/test_urn_spec_v3.py  file_ready=True
    [·] test_v3_one_test_urn_per_file
    [·] test_v3_acceptance_journey_mutual_exclusion
    [·] test_v3_phase_and_layer_values
    [·] test_v3_journey_tests_have_train_header
    [·] test_v3_reserved_slugs
    [·] test_v3_components_have_tested_by
    [·] test_v3_train_infra_assembly_only

SUMMARY: file_ready=24  blocked_files=29 (30 blocked assertions)  unbound_only_files=56
A file is deletable only when EVERY assertion is covered or unbound. Catch_matrix oracle functions (⚠) require a corpus edit in the same change.
