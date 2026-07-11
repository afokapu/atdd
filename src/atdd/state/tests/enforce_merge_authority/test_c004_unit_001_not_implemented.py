# URN: test:enforce-merge-authority:enforce-rule-disposition:C004-UNIT-001-not-implemented
# Acceptance: acc:enforce-merge-authority:C004-UNIT-001-not-implemented
# WMBT: wmbt:enforce-merge-authority:C004
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: a convention node authored by train 0006-state-projection that ships disposition advisory with no stated precondition is refused by the disposition validator, which names the rule and the unpaid-advisory clause. Refs #1400.
"""An advisory node with no precondition is refused (C004-UNIT-001).

wagon: enforce-merge-authority | feature: enforce-rule-disposition | phase: RED
WMBT: wmbt:enforce-merge-authority:C004

``disposition: advisory`` exists to grandfather a corpus that already violates a rule you
cannot fix today. The projection corpus starts **empty** — there is nothing to grandfather.
A new rule that ships advisory therefore reports a real violation and is ignored, and by
the time anyone looks, the corpus it was written to protect has grown a backlog of exactly
the fault it was meant to catch.

So the gate: a node this train authors may not ship advisory with no stated precondition.
Refs #1400.
"""
from __future__ import annotations

from atdd.state import dispositions
from atdd.state.dispositions import check_node


def test_c004_unit_001_not_implemented() -> None:
    """The unpaid advisory is refused, named, and told what it is missing."""
    node = {
        "id": "coder.projection.canonical-bytes",
        "name": "canonical-bytes",
        "disposition": "advisory",   # ...with no precondition and no discharging issue
    }

    violations = check_node(node, source="projection.convention.yaml")

    assert violations, "a node authored by this train may not ship advisory unpaid"
    violation = violations[0]
    assert violation.rule_id == "coder.projection.canonical-bytes"
    assert violation.clause == dispositions.CLAUSE_UNPAID_ADVISORY
    assert violation.source == "projection.convention.yaml"

    # The refusal names BOTH things the node would have to carry to be admissible.
    assert dispositions.PRECONDITION_KEY in violation.detail
    assert dispositions.DISCHARGED_BY_KEY in violation.detail
    assert "nothing to grandfather" in violation.detail

    # Half-paying is not paying: a precondition with no issue to discharge it is debt with
    # nobody's name on it.
    assert check_node({**node, dispositions.PRECONDITION_KEY: "once #1400 lands"})
    assert check_node({**node, dispositions.DISCHARGED_BY_KEY: "#1401"})

    # A node that declares no disposition at all is refused too — silence is not strict.
    silent = check_node({"id": "coder.projection.quiet"})
    assert silent[0].clause == dispositions.CLAUSE_MISSING_DISPOSITION
