# URN: test:reconcile-dispositions:reconcile-dispositions:D001-UNIT-002-three-namespaces-named-separately-without-collision
# Acceptance: acc:reconcile-dispositions:D001-UNIT-002-three-namespaces-named-separately-without-collision
# WMBT: wmbt:reconcile-dispositions:D001
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""D001-UNIT-002 — the model names the treatment vocabulary, the wiring value
``bound``, and the ``disposition_gate`` validator name as three distinct
constants that never conflate."""
from __future__ import annotations


def test_d001_unit_002_three_namespaces_named_separately_without_collision():
    from atdd.enforce.dispositions import (
        TREATMENT_DISPOSITIONS,
        BOUND_DISPOSITION,
        DISPOSITION_GATE,
    )

    assert BOUND_DISPOSITION == "bound"
    assert DISPOSITION_GATE == "disposition_gate"
    # No single symbol conflates a treatment with the wiring value or gate name.
    assert BOUND_DISPOSITION not in TREATMENT_DISPOSITIONS
    assert DISPOSITION_GATE not in TREATMENT_DISPOSITIONS
    assert BOUND_DISPOSITION != DISPOSITION_GATE
