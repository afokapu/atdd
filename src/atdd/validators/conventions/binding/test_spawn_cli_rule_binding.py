# URN: test:validate-conventions:binding-variants:spawn_cli_rule_binding
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `binding/spawn_cli_rule_binding` (#1212).

Wires the `coach.spawn.atdd-spawn-cli` rule onto the official execution path
(REAL composed graph -> `archetype.TEMPLATES[*].evaluate(graph, config)`) and
proves legacy parity by differential fault injection.

The legacy reverse-coherence binder (`test_e001_unit_001_spawn_cli_launches_session`)
binds `_RULE = bind_rule("coach.spawn.atdd-spawn-cli")` at import time, so renaming
the rule_id in the convention makes BOTH the convention roundtrip path and the
legacy validator fail on identical input.
"""
from __future__ import annotations

from atdd.validators.conventions.binding.archetype import TEMPLATE_IDS
from atdd.validators.conventions.binding import _parity_support as P

FAMILY = "binding"
TEMPLATE = "declaration_to_implementation_binding"
PARITY_TEMPLATE = "emitted_identity_roundtrip"
VARIANT = "spawn_cli_rule_binding"
QUESTION = 'Does a declaration point to a real implementation, validator, or artifact that claims to enforce it?'
SELECTOR = 'rule/declaration nodes where enforcement requires implementation'
TRAVERSAL = 'declaration node -> implementation_ref -> implementation index'
INVARIANT = 'implementation exists and declares compatibility with the declaration'
AUTO_CAPTURE = 'a new node is included if it declares enforcement=validator or equivalent implementation binding metadata'
FAILURE_EVIDENCE = ['declaration_node', 'implementation_ref', 'missing_or_incompatible_implementation', 'declaration_location']
LEGACY_PARITY_SOURCES = ['src/atdd/coach/validators/test_e001_unit_001_spawn_cli_launches_session.py']

RULE_ID = "coach.spawn.atdd-spawn-cli"
CONVENTION = "src/atdd/coach/conventions/spawn.convention.yaml"
LEGACY_NODEID = (
    "src/atdd/coach/validators/test_e001_unit_001_spawn_cli_launches_session.py"
    "::test_spawn_emits_agent_spawned_event_conforming_to_schema"
)


def test_spawn_cli_rule_binding_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in binding archetype"
    assert PARITY_TEMPLATE in TEMPLATE_IDS, f"{PARITY_TEMPLATE} not in binding archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"


def test_spawn_cli_rule_binding_clean_baseline() -> None:
    P.assert_clean_baseline(VARIANT, P.repo_root())


def test_spawn_cli_rule_binding_legacy_parity() -> None:
    result = P.assert_fault_parity(VARIANT, CONVENTION, RULE_ID, LEGACY_NODEID, P.repo_root())
    assert result["verdict"] == "both"
