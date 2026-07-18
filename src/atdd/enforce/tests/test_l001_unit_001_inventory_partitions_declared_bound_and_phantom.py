# URN: test:bind-extension-conventions:bind-extension-conventions:L001-UNIT-001-inventory-partitions-declared-bound-and-phantom
# Acceptance: acc:bind-extension-conventions:L001-UNIT-001-inventory-partitions-declared-bound-and-phantom
# WMBT: wmbt:bind-extension-conventions:L001
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""RED Test for acc:bind-extension-conventions:L001-UNIT-001-inventory-partitions-declared-bound-and-phantom.

The binding-gap inventory partitions a declared-node-with-disposition map and a
bound-convention set into overlap, declared-not-bound, and bound-not-declared,
and splits declared-not-bound into the gating obligations and the
documentation-only exemptions.
"""
from __future__ import annotations

from atdd.enforce.binding_gap import compute_binding_gap


def test_inventory_partitions_declared_bound_and_phantom() -> None:
    declared = {
        "a.strict": "strict",
        "b.strict": "strict",
        "c.advisory": "advisory",
        "d.documentation-only": "documentation-only",
        "e.suppress-and-clean": "suppress-and-clean",
        "f.strict": "strict",
    }
    bound = {"a.strict", "z.phantom"}

    gap = compute_binding_gap(declared, bound)

    # The three-way partition over (declared, bound).
    assert gap.overlap == {"a.strict"}
    assert gap.declared_not_bound == {
        "b.strict",
        "c.advisory",
        "d.documentation-only",
        "e.suppress-and-clean",
        "f.strict",
    }
    assert gap.bound_not_declared == {"z.phantom"}

    # declared-not-bound splits into gating obligations and doc-only exemptions.
    assert gap.gating_unbound == {"b.strict", "c.advisory", "e.suppress-and-clean", "f.strict"}
    assert gap.doc_only_unbound == {"d.documentation-only"}
