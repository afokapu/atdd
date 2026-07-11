# URN: test:reconcile-dispositions:reconcile-dispositions:D001-UNIT-001-treatment-vocabulary-is-the-four-treatments
# Acceptance: acc:reconcile-dispositions:D001-UNIT-001-treatment-vocabulary-is-the-four-treatments
# WMBT: wmbt:reconcile-dispositions:D001
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""D001-UNIT-001 — the treatment namespace enumerates exactly the four
metadata.disposition treatments and excludes the wiring value ``bound``."""
from __future__ import annotations


def test_d001_unit_001_treatment_vocabulary_is_the_four_treatments():
    from atdd.enforce.dispositions import (
        TREATMENT_DISPOSITIONS,
        STRICT,
        ADVISORY,
        SUPPRESS_AND_CLEAN,
        DOCUMENTATION_ONLY,
        BOUND_DISPOSITION,
    )

    assert TREATMENT_DISPOSITIONS == frozenset(
        {STRICT, ADVISORY, SUPPRESS_AND_CLEAN, DOCUMENTATION_ONLY}
    )
    assert TREATMENT_DISPOSITIONS == frozenset(
        {"strict", "advisory", "suppress-and-clean", "documentation-only"}
    )
    # The wiring value is NOT a treatment — the two namespaces do not overlap.
    assert BOUND_DISPOSITION not in TREATMENT_DISPOSITIONS
