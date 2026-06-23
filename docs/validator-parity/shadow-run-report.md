# Shadow-Run Report (#1207, Phase 1)

Compares the legacy persona validators against the new convention validator variants (#1206), run in parallel.

## Summary

- P0 buildable legacy validators: 32
- P0 covered by a convention variant: 32
- **Unresolved P0: 0**
- Legacy and convention suites run in parallel; no failure-class regression observed.
- Decision: keep legacy as compatibility shims during transition; no deletion in this phase.

## P0 coverage detail

| convention variant | legacy source(s) | same failure class | decision |
|---|---|---|---|
| `src/atdd/validators/conventions/binding/test_no_hardcoded_rule_severity.py` | `src/atdd/coach/validators/test_no_hardcoded_rule_severity.py` | yes (template-bound) | replace (shadow then promote) |
| `src/atdd/validators/conventions/binding/test_rule_validator_binding.py` | `src/atdd/coach/validators/test_rule_validator_binding.py` | yes (template-bound) | replace (shadow then promote) |
| `src/atdd/validators/conventions/binding/test_validator_binding_bidirectional.py` | `src/atdd/tester/validators/test_repo_validator_binding.py` | yes (template-bound) | replace (shadow then promote) |
| `src/atdd/validators/conventions/composition/test_package_data_ships_convention_nodes.py` | `src/atdd/coach/validators/test_composition_data_shipped.py` | yes (template-bound) | replace (shadow then promote) |
| `src/atdd/validators/conventions/grammar/test_acceptance_urn_grammar.py` | `src/atdd/tester/validators/test_acceptance_urn_separator.py` | yes (template-bound) | replace (shadow then promote) |
| `src/atdd/validators/conventions/grammar/test_artifact_naming_grammar.py` | `src/atdd/tester/validators/test_artifact_naming_category.py` | yes (template-bound) | replace (shadow then promote) |
| `src/atdd/validators/conventions/grammar/test_contracts_path_grammar.py` | `src/atdd/tester/validators/test_contracts_structure.py` | yes (template-bound) | replace (shadow then promote) |
| `src/atdd/validators/conventions/grammar/test_freedom_layer_bash_scope_grammar.py` | `src/atdd/coach/validators/test_e032_unit_002_validator_rejects_unscoped_bash_entry.py` | yes (template-bound) | replace (shadow then promote) |
| `src/atdd/validators/conventions/grammar/test_init_file_urn_grammar.py` | `src/atdd/coder/validators/test_init_file_urns.py` | yes (template-bound) | replace (shadow then promote) |
| `src/atdd/validators/conventions/grammar/test_python_test_naming.py` | `src/atdd/tester/validators/test_python_test_naming.py` | yes (template-bound) | replace (shadow then promote) |
| `src/atdd/validators/conventions/grammar/test_telemetry_naming_grammar.py` | `src/atdd/tester/validators/test_telemetry_structure.py` | yes (template-bound) | replace (shadow then promote) |
| `src/atdd/validators/conventions/grammar/test_theme_must_be_canonical.py` | `src/atdd/planner/validators/test_theme_must_be_canonical.py` | yes (template-bound) | replace (shadow then promote) |
| `src/atdd/validators/conventions/grammar/test_train_urn_grammar.py` | `src/atdd/coder/validators/test_train_urns.py` | yes (template-bound) | replace (shadow then promote) |
| `src/atdd/validators/conventions/grammar/test_typescript_test_naming.py` | `src/atdd/tester/validators/test_typescript_test_naming.py` | yes (template-bound) | replace (shadow then promote) |
| `src/atdd/validators/conventions/grammar/test_urn_header_spec_v3.py` | `src/atdd/tester/validators/test_urn_spec_v3.py` | yes (template-bound) | replace (shadow then promote) |
| `src/atdd/validators/conventions/grammar/test_wmbt_vocabulary.py` | `src/atdd/planner/validators/test_wmbt_vocabulary.py` | yes (template-bound) | replace (shadow then promote) |
| `src/atdd/validators/conventions/resolution/test_contract_consumer_resolution.py` | `src/atdd/coach/validators/test_validate_contract_consumers.py` | yes (template-bound) | replace (shadow then promote) |
| `src/atdd/validators/conventions/resolution/test_draft_wagon_registry.py` | `src/atdd/planner/validators/test_draft_wagon_registry.py` | yes (template-bound) | replace (shadow then promote) |
| `src/atdd/validators/conventions/resolution/test_metric_implementation_resolves.py` | `src/atdd/tester/validators/test_metric_implementation.py` | yes (template-bound) | replace (shadow then promote) |
| `src/atdd/validators/conventions/resolution/test_plan_cross_refs.py` | `src/atdd/planner/validators/test_plan_cross_refs.py` | yes (template-bound) | replace (shadow then promote) |
| `src/atdd/validators/conventions/resolution/test_plan_urn_resolution.py` | `src/atdd/planner/validators/test_plan_urn_resolution.py` | yes (template-bound) | replace (shadow then promote) |
| `src/atdd/validators/conventions/resolution/test_route_train_wagon_chain.py` | `src/atdd/coder/validators/test_route_train_wagon_coverage.py` | yes (template-bound) | replace (shadow then promote) |
| `src/atdd/validators/conventions/resolution/test_security_ref_resolution.py` | `src/atdd/tester/validators/test_security_ref_binding.py` | yes (template-bound) | replace (shadow then promote) |
| `src/atdd/validators/conventions/resolution/test_train_validation.py` | `src/atdd/planner/validators/test_train_validation.py` | yes (template-bound) | replace (shadow then promote) |
| `src/atdd/validators/conventions/resolution/test_urn_traceability.py` | `src/atdd/coach/validators/test_urn_traceability.py` | yes (template-bound) | replace (shadow then promote) |
| `src/atdd/validators/conventions/resolution/test_wagon_urn_chain.py` | `src/atdd/planner/validators/test_wagon_urn_chain.py` | yes (template-bound) | replace (shadow then promote) |
| `src/atdd/validators/conventions/schema/test_contract_schema_conformance.py` | `src/atdd/tester/validators/test_contract_schema_compliance.py` | yes (template-bound) | replace (shadow then promote) |
| `src/atdd/validators/conventions/schema/test_dispatch_map_is_registry.py` | `src/atdd/planner/validators/test_dispatch_registry.py` | yes (template-bound) | replace (shadow then promote) |
| `src/atdd/validators/conventions/schema/test_plan_wagons.py` | `src/atdd/planner/validators/test_plan_wagons.py` | yes (template-bound) | replace (shadow then promote) |
| `src/atdd/validators/conventions/schema/test_train_yaml_render_metadata.py` | `src/atdd/coder/validators/test_train_yaml_render_metadata.py` | yes (template-bound) | replace (shadow then promote) |
| `src/atdd/validators/conventions/uniqueness/test_plan_uniqueness.py` | `src/atdd/planner/validators/test_plan_uniqueness.py` | yes (template-bound) | replace (shadow then promote) |
| `src/atdd/validators/conventions/uniqueness/test_rule_id_uniqueness.py` | `src/atdd/coach/validators/test_rule_id_uniqueness.py` | yes (template-bound) | replace (shadow then promote) |
