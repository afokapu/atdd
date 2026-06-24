# URN: test:validate-conventions:coherence-variants:train_family_matches_terminal_contract
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `coherence/train_family_matches_terminal_contract` (#1206).

Instantiates the `coherence/resolved_fact_agreement` template against the composed convention
graph. Traversal execution lands incrementally on the _support graph engine;
this module fixes the variant's contract + legacy parity binding and is runnable
in parallel with legacy validators (imports no persona validator module).
"""
from __future__ import annotations

from atdd.validators.conventions.coherence import _parity
from atdd.validators.conventions.coherence.archetype import (
    TEMPLATE_IDS,
    resolved_fact_agreement,
)
from atdd.validators.conventions.coherence.fixtures import (
    INVALID_FRAGMENTS,
    VALID_FRAGMENTS,
)

FAMILY = "coherence"
TEMPLATE = "resolved_fact_agreement"
VARIANT = "train_family_matches_terminal_contract"
QUESTION = 'After references resolve, do the resolved facts agree with each other?'
SELECTOR = 'nodes declaring coherence checks or semantic comparison rules'
TRAVERSAL = 'source node -> resolved fact A; source node -> resolved fact B; compare A and B'
INVARIANT = 'facts satisfy comparison predicate'
AUTO_CAPTURE = 'partial; a new node is included only if it declares a known coherence predicate'
FAILURE_EVIDENCE = ['source_node', 'fact_a', 'fact_b', 'predicate', 'actual_values']
LEGACY_PARITY_SOURCES = ['src/atdd/planner/validators/test_train_family_matches_terminal_contract.py']


def test_train_family_matches_terminal_contract_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in coherence archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"


# --- executable graph-question tests ---------------------------------------
# PARITY: full subprocess differential. Clean baseline is 0 (only train 0002
# declares a family, `behavior`, with a non-receipt terminal -> agrees). The fault
# (flip 0002 to family=delivery while its terminal is NOT a commit-receipt) is caught
# by BOTH the convention evaluator and the disposition-gated legacy target.
_LEGACY_NODEID = (
    "src/atdd/planner/validators/test_train_family_matches_terminal_contract.py"
    "::test_real_trains_family_matches_terminal_contract"
)
_TRAIN_FILE = "plan/_trains/0002-coach-drives-lifecycle.yaml"


def test_clean_baseline_is_zero() -> None:
    assert _parity.conv_violations(VARIANT) == []


def test_fault_injection_legacy_parity() -> None:
    """Flip a real train's family to disagree with its terminal artifact; assert
    BOTH the convention evaluator and the legacy validator catch it; revert."""
    root = _parity.repo_root()
    with _parity.patch_file(root, _TRAIN_FILE, "family: behavior", "family: delivery"):
        conv = _parity.conv_violations(VARIANT, root)
        legacy = _parity.legacy_caught(_LEGACY_NODEID, root)
    assert conv, "convention evaluator did not catch the family/terminal disagreement"
    assert legacy, "legacy validator did not catch the family/terminal disagreement"
    assert _parity.conv_violations(VARIANT, root) == [], "fault did not revert cleanly"


def test_invalid_fragment_is_caught() -> None:
    out = resolved_fact_agreement(INVALID_FRAGMENTS[VARIANT], {"variant": VARIANT})
    assert len(out) == 1 and out[0]["fact_a"] == "delivery", out


def test_valid_fragment_is_clean() -> None:
    assert resolved_fact_agreement(VALID_FRAGMENTS[VARIANT], {"variant": VARIANT}) == []
