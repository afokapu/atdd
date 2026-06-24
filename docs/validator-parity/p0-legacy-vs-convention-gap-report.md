# P0 Legacy-vs-Convention Behavioral Gap Report (#1206/#1207)

Measured per-pair behavioral parity state. **VERIFIED requires a real diff proving the convention variant catches the same failure class as the actual legacy validator.** None are VERIFIED yet.

## Summary

- P0 pairs: **32**
- behaviorally VERIFIED vs legacy: **0**
- GAP (convention engine inert on real graph / does not replicate legacy): **32**
- NO_ENGINE: **0**  ·  REVIEW: **0**  ·  ERROR: **0**
- legacy validators exposing a callable `collect_violations()` API: **2/32** (rest are pytest-coupled — need refactor or fault-injection to diff)

## Why no pair is verified

- Template evaluators key on synthetic fields (refs/grammar/enforcement/…) that real composed-graph nodes do not carry, so they detect nothing on the real repo — they pass only against hand-authored fixtures.
- 30/32 legacy validators have no callable API to drive on identical inputs.

## Per-pair

| legacy validator | family/template | legacy callable | conv detects (real graph) | verdict | reason |
|---|---|---|---|---|---|
| test_composition_data_shipped.py | composition/composed_graph_loads | no | 0 | GAP | convention engine inert on real graph (fixture-only); does not replicate legacy rule |
| test_e032_unit_002_validator_rejects_unscoped_bash_entry.py | grammar/identifier_grammar_conformance | no | 0 | GAP | convention engine inert on real graph (fixture-only); does not replicate legacy rule |
| test_no_hardcoded_rule_severity.py | binding/declaration_to_implementation_binding | no | 0 | GAP | convention engine inert on real graph (fixture-only); does not replicate legacy rule |
| test_rule_id_uniqueness.py | uniqueness/scoped_identifier_uniqueness | no | 0 | GAP | convention engine inert on real graph (fixture-only); does not replicate legacy rule |
| test_rule_validator_binding.py | binding/declaration_to_implementation_binding | no | 0 | GAP | convention engine inert on real graph (fixture-only); does not replicate legacy rule |
| test_urn_traceability.py | resolution/reference_chain_resolution | no | 0 | GAP | convention engine inert on real graph (fixture-only); does not replicate legacy rule |
| test_validate_contract_consumers.py | resolution/artifact_reference_resolution | no | 0 | GAP | convention engine inert on real graph (fixture-only); does not replicate legacy rule |
| test_init_file_urns.py | grammar/identifier_grammar_conformance | no | 0 | GAP | convention engine inert on real graph (fixture-only); does not replicate legacy rule |
| test_route_train_wagon_coverage.py | resolution/reference_chain_resolution | no | 0 | GAP | convention engine inert on real graph (fixture-only); does not replicate legacy rule |
| test_train_urns.py | grammar/identifier_grammar_conformance | no | 0 | GAP | convention engine inert on real graph (fixture-only); does not replicate legacy rule |
| test_train_yaml_render_metadata.py | schema/node_schema_conformance | no | 0 | GAP | convention engine inert on real graph (fixture-only); does not replicate legacy rule |
| test_dispatch_registry.py | schema/node_schema_conformance | no | 0 | GAP | convention engine inert on real graph (fixture-only); does not replicate legacy rule |
| test_draft_wagon_registry.py | resolution/artifact_reference_resolution | no | 0 | GAP | convention engine inert on real graph (fixture-only); does not replicate legacy rule |
| test_plan_cross_refs.py | resolution/artifact_reference_resolution | no | 0 | GAP | convention engine inert on real graph (fixture-only); does not replicate legacy rule |
| test_plan_uniqueness.py | uniqueness/scoped_identifier_uniqueness | no | 0 | GAP | convention engine inert on real graph (fixture-only); does not replicate legacy rule |
| test_plan_urn_resolution.py | resolution/artifact_reference_resolution | no | 0 | GAP | convention engine inert on real graph (fixture-only); does not replicate legacy rule |
| test_plan_wagons.py | schema/node_schema_conformance | no | 0 | GAP | convention engine inert on real graph (fixture-only); does not replicate legacy rule |
| test_theme_must_be_canonical.py | grammar/identifier_grammar_conformance | no | 0 | GAP | convention engine inert on real graph (fixture-only); does not replicate legacy rule |
| test_train_validation.py | resolution/direct_reference_resolution | no | 0 | GAP | convention engine inert on real graph (fixture-only); does not replicate legacy rule |
| test_wagon_urn_chain.py | resolution/reference_chain_resolution | no | 0 | GAP | convention engine inert on real graph (fixture-only); does not replicate legacy rule |
| test_wmbt_vocabulary.py | grammar/identifier_grammar_conformance | no | 0 | GAP | convention engine inert on real graph (fixture-only); does not replicate legacy rule |
| test_acceptance_urn_separator.py | grammar/identifier_grammar_conformance | no | 0 | GAP | convention engine inert on real graph (fixture-only); does not replicate legacy rule |
| test_artifact_naming_category.py | grammar/identifier_grammar_conformance | no | 0 | GAP | convention engine inert on real graph (fixture-only); does not replicate legacy rule |
| test_contract_schema_compliance.py | schema/node_schema_conformance | no | 0 | GAP | convention engine inert on real graph (fixture-only); does not replicate legacy rule |
| test_contracts_structure.py | grammar/identifier_grammar_conformance | no | 0 | GAP | convention engine inert on real graph (fixture-only); does not replicate legacy rule |
| test_metric_implementation.py | resolution/artifact_reference_resolution | yes | 0 | GAP | convention engine inert on real graph (fixture-only); does not replicate legacy rule |
| test_python_test_naming.py | grammar/identifier_grammar_conformance | no | 0 | GAP | convention engine inert on real graph (fixture-only); does not replicate legacy rule |
| test_repo_validator_binding.py | binding/declaration_to_implementation_binding | yes | 0 | GAP | convention engine inert on real graph (fixture-only); does not replicate legacy rule |
| test_security_ref_binding.py | resolution/direct_reference_resolution | no | 0 | GAP | convention engine inert on real graph (fixture-only); does not replicate legacy rule |
| test_telemetry_structure.py | grammar/identifier_grammar_conformance | no | 0 | GAP | convention engine inert on real graph (fixture-only); does not replicate legacy rule |
| test_typescript_test_naming.py | grammar/identifier_grammar_conformance | no | 0 | GAP | convention engine inert on real graph (fixture-only); does not replicate legacy rule |
| test_urn_spec_v3.py | grammar/identifier_grammar_conformance | no | 0 | GAP | convention engine inert on real graph (fixture-only); does not replicate legacy rule |

## Path to VERIFIED (per pair)

1. Implement the convention check to replicate the legacy rule against the REAL composed graph (not synthetic fixtures).
2. Give the legacy validator a callable `collect_violations(repo_root)` OR a fault-injection fixture.
3. Diff: inject the violation → assert BOTH legacy and convention flag it; assert both clean on the good input.
4. Only then mark the pair VERIFIED and check it off the decommission gate.

Until then: **legacy authoritative, decommission BLOCKED.**
