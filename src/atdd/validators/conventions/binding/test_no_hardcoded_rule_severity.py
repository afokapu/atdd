# URN: test:validate-conventions:binding-variants:no_hardcoded_rule_severity
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `binding/no_hardcoded_rule_severity` (#1206/#1212).

Wires the variant onto the official execution path — the REAL composed convention
graph evaluated through `archetype.TEMPLATES[*].evaluate(graph, config)` — and
proves legacy parity by differential fault injection.

Declared family template: `declaration_to_implementation_binding`. The executable
parity fault (renaming the rule_id so its declared validator no longer emits it)
is a declaration<->implementation roundtrip break, exercised through the sibling
`emitted_identity_roundtrip` template; the legacy reverse-coherence binder
(`test_no_hardcoded_rule_severity`) calls `bind_rule(<id>)` at import time, so the
rename makes BOTH paths fail on identical input.
"""
from __future__ import annotations

from atdd.validators.conventions.binding.archetype import TEMPLATE_IDS
from atdd.validators.conventions.binding import _parity_support as P

FAMILY = "binding"
TEMPLATE = "declaration_to_implementation_binding"
PARITY_TEMPLATE = "emitted_identity_roundtrip"
VARIANT = "no_hardcoded_rule_severity"
QUESTION = 'Does a declaration point to a real implementation, validator, or artifact that claims to enforce it?'
SELECTOR = 'rule/declaration nodes where enforcement requires implementation'
TRAVERSAL = 'declaration node -> implementation_ref -> implementation index'
INVARIANT = 'implementation exists and declares compatibility with the declaration'
AUTO_CAPTURE = 'a new node is included if it declares enforcement=validator or equivalent implementation binding metadata'
FAILURE_EVIDENCE = ['declaration_node', 'implementation_ref', 'missing_or_incompatible_implementation', 'declaration_location']
LEGACY_PARITY_SOURCES = ['src/atdd/coach/validators/test_no_hardcoded_rule_severity.py']

# Variant-specific binding under test (real convention + the rule the legacy
# reverse-coherence binder asserts).
RULE_ID = "coach.rule-id.no-hardcoded-rule-severity"
# Authoritative home is the single-node nodes/ file (#1225); the rule was migrated
# out of the monolith rule-id.convention.yaml, so the rename-injection targets it there.
CONVENTION = (
    "src/atdd/coach/conventions/nodes/coach.rule-id.no-hardcoded-rule-severity.convention.yaml"
)
def test_no_hardcoded_rule_severity_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in binding archetype"
    assert PARITY_TEMPLATE in TEMPLATE_IDS, f"{PARITY_TEMPLATE} not in binding archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"


def test_no_hardcoded_rule_severity_clean_baseline(clean_convention_graph) -> None:
    """Both binding templates flag nothing on the real repo for this variant."""
    P.assert_clean_baseline(VARIANT, P.repo_root(), graph=clean_convention_graph)


def test_no_hardcoded_rule_severity_convention_fault() -> None:
    """Inject the binding fault; the convention path catches it (oracle retired #1365)."""
    P.assert_fault_convention_only(VARIANT, CONVENTION, RULE_ID, P.repo_root())
