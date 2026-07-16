# URN: test:bind-extension-conventions:bind-extension-conventions:L001-UNIT-002-inventory-names-every-gating-unbound-and-phantom
# Acceptance: acc:bind-extension-conventions:L001-UNIT-002-inventory-names-every-gating-unbound-and-phantom
# WMBT: wmbt:bind-extension-conventions:L001
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""RED Test for acc:bind-extension-conventions:L001-UNIT-002-inventory-names-every-gating-unbound-and-phantom.

The inventory names each member — not just counts. Every declared-but-unbound
node is classified as exactly one of gating or documentation-only (an exhaustive,
disjoint split), and every bound-but-undeclared phantom is named.
"""
from __future__ import annotations

from atdd.enforce.binding_gap import compute_binding_gap


def test_inventory_names_every_gating_unbound_and_phantom() -> None:
    declared = {
        "coder.design.token-color": "strict",
        "coder.boundaries.xlang-contract": "advisory",
        "coder.performance.perf": "documentation-only",
        "tester.migration.naming": "documentation-only",
        "coder.design.primitives": "strict",  # bound (overlap)
    }
    bound = {
        "coder.design.primitives",
        "tester.smoke.no-collaborator-substitution",  # phantom vs this declared set
    }

    gap = compute_binding_gap(declared, bound)

    # Every gating-unbound obligation is named.
    assert gap.gating_unbound == {"coder.design.token-color", "coder.boundaries.xlang-contract"}
    # Every documentation-only exemption is named and kept out of the gating set.
    assert gap.doc_only_unbound == {"coder.performance.perf", "tester.migration.naming"}
    # Every phantom is named.
    assert gap.bound_not_declared == {"tester.smoke.no-collaborator-substitution"}

    # The split of declared-not-bound is exhaustive and disjoint.
    assert gap.gating_unbound | gap.doc_only_unbound == gap.declared_not_bound
    assert gap.gating_unbound.isdisjoint(gap.doc_only_unbound)
