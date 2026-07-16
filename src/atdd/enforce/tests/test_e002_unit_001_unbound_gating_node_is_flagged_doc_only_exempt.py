# URN: test:bind-extension-conventions:bind-extension-conventions:E002-UNIT-001-unbound-gating-node-is-flagged-doc-only-exempt
# Acceptance: acc:bind-extension-conventions:E002-UNIT-001-unbound-gating-node-is-flagged-doc-only-exempt
# WMBT: wmbt:bind-extension-conventions:E002
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""RED Test for acc:bind-extension-conventions:E002-UNIT-001-unbound-gating-node-is-flagged-doc-only-exempt.

An unbound gating node (strict/advisory/suppress-and-clean) is reported as a
coverage gap; an unbound documentation-only node is exempt and never reported.
"""
from __future__ import annotations

from atdd.enforce.gating import find_unbound_gating_nodes


def test_unbound_gating_node_is_flagged_doc_only_exempt() -> None:
    declared = {
        "a.strict": "strict",
        "b.advisory": "advisory",
        "c.suppress-and-clean": "suppress-and-clean",
        "d.documentation-only": "documentation-only",
        "e.strict": "strict",  # bound
    }
    bound = {"e.strict"}

    unbound = find_unbound_gating_nodes(declared, bound)

    # Every unbound gating node is flagged, sorted, and the doc-only node is exempt.
    assert unbound == ["a.strict", "b.advisory", "c.suppress-and-clean"]
    assert "d.documentation-only" not in unbound
