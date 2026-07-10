"""RED tests for WMBT D001 — disposition-namespace-model (#1424).

Feature: feature:reconcile-dispositions:reconcile-dispositions

The three distinct things spelled "disposition" must be named as three separate,
importable namespaces under ``atdd.enforce.dispositions``:

  1. TREATMENT — a node's ``metadata.disposition`` vocabulary
     {strict, advisory, suppress-and-clean, documentation-only}.
  2. WIRING — the ``binding.lock`` value ``bound`` (NOT a treatment).
  3. GATE — the ``disposition_gate`` validator name.
"""
from __future__ import annotations

import importlib


# Acceptance: acc:reconcile-dispositions:D001-UNIT-001-treatment-vocabulary-is-the-four-treatments
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


# Acceptance: acc:reconcile-dispositions:D001-UNIT-002-three-namespaces-named-separately-without-collision
def test_d001_unit_002_three_namespaces_named_separately_without_collision():
    from atdd.enforce.dispositions import (
        TREATMENT_DISPOSITIONS,
        BOUND_DISPOSITION,
        DISPOSITION_GATE,
    )

    assert BOUND_DISPOSITION == "bound"
    assert DISPOSITION_GATE == "disposition_gate"
    # No single symbol conflates a treatment with the wiring value or the gate name.
    assert BOUND_DISPOSITION not in TREATMENT_DISPOSITIONS
    assert DISPOSITION_GATE not in TREATMENT_DISPOSITIONS
    assert BOUND_DISPOSITION != DISPOSITION_GATE


# Acceptance: acc:reconcile-dispositions:D001-SMOKE-001-model-imports-cleanly-in-the-installed-package
def test_d001_smoke_001_model_imports_cleanly_in_the_installed_package():
    module = importlib.import_module("atdd.enforce.dispositions")
    # The three namespace anchors are reachable as named module attributes.
    assert isinstance(getattr(module, "TREATMENT_DISPOSITIONS"), frozenset)
    assert getattr(module, "BOUND_DISPOSITION") == "bound"
    assert getattr(module, "DISPOSITION_GATE") == "disposition_gate"
