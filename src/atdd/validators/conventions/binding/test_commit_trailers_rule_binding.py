# URN: test:validate-conventions:binding-variants:commit_trailers_rule_binding
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `binding/commit_trailers_rule_binding` (#1212).

Wires the `coach.commit-trailers.*` rule family onto the official execution path
(REAL composed graph -> `archetype.TEMPLATES[*].evaluate(graph, config)`) and
proves legacy parity by differential fault injection.

The legacy reverse-coherence binder (`test_commit_trailers_binding`) calls
`bind_rule("coach.commit-trailers.phase-required")` (and siblings) at import time,
so renaming the rule_id in the convention makes BOTH the convention roundtrip path
and the legacy validator fail on identical input — a real declaration<->
implementation binding break.
"""
from __future__ import annotations

from atdd.validators.conventions.binding.archetype import TEMPLATE_IDS
from atdd.validators.conventions.binding import _parity_support as P

FAMILY = "binding"
TEMPLATE = "declaration_to_implementation_binding"
PARITY_TEMPLATE = "emitted_identity_roundtrip"
VARIANT = "commit_trailers_rule_binding"
QUESTION = 'Does a declaration point to a real implementation, validator, or artifact that claims to enforce it?'
SELECTOR = 'rule/declaration nodes where enforcement requires implementation'
TRAVERSAL = 'declaration node -> implementation_ref -> implementation index'
INVARIANT = 'implementation exists and declares compatibility with the declaration'
AUTO_CAPTURE = 'a new node is included if it declares enforcement=validator or equivalent implementation binding metadata'
FAILURE_EVIDENCE = ['declaration_node', 'implementation_ref', 'missing_or_incompatible_implementation', 'declaration_location']
LEGACY_PARITY_SOURCES = ['src/atdd/coach/validators/test_commit_trailers_binding.py']

# Any one rule of the family proves the binding; phase-required is bound first in
# the legacy module's import-time block.
RULE_ID = "coach.commit-trailers.phase-required"
CONVENTION = "src/atdd/coach/conventions/commit-trailers.convention.yaml"
LEGACY_NODEID = (
    "src/atdd/coach/validators/test_commit_trailers_binding.py"
    "::test_commit_trailers_rule_family_emits_each_required_trailer_id"
)


def test_commit_trailers_rule_binding_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in binding archetype"
    assert PARITY_TEMPLATE in TEMPLATE_IDS, f"{PARITY_TEMPLATE} not in binding archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"


def test_commit_trailers_rule_binding_clean_baseline() -> None:
    P.assert_clean_baseline(VARIANT, P.repo_root())


def test_commit_trailers_rule_binding_legacy_parity() -> None:
    result = P.assert_fault_parity(VARIANT, CONVENTION, RULE_ID, LEGACY_NODEID, P.repo_root())
    assert result["verdict"] == "both"
