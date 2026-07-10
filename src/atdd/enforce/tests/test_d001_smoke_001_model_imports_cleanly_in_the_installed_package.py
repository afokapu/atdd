# URN: test:reconcile-dispositions:D001-SMOKE-001-model-imports-cleanly-in-the-installed-package
# Acceptance: acc:reconcile-dispositions:D001-SMOKE-001-model-imports-cleanly-in-the-installed-package
# WMBT: wmbt:reconcile-dispositions:D001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""D001-SMOKE-001 — the disposition model imports from the installed
``atdd.enforce`` package and exposes the three namespaces without an import
error."""
from __future__ import annotations

import importlib


def test_d001_smoke_001_model_imports_cleanly_in_the_installed_package():
    module = importlib.import_module("atdd.enforce.dispositions")
    # The three namespace anchors are reachable as named module attributes.
    assert isinstance(getattr(module, "TREATMENT_DISPOSITIONS"), frozenset)
    assert getattr(module, "BOUND_DISPOSITION") == "bound"
    assert getattr(module, "DISPOSITION_GATE") == "disposition_gate"
