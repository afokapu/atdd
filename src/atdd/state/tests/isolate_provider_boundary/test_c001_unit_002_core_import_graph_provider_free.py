# URN: test:isolate-provider-boundary:enforce-import-boundary:C001-UNIT-002-core-import-graph-provider-free
# Acceptance: acc:isolate-provider-boundary:C001-UNIT-002-core-import-graph-provider-free
# WMBT: wmbt:isolate-provider-boundary:C001
# Phase: GREEN
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:isolate-provider-boundary:C001-UNIT-002-core-import-graph-provider-free — fails until the isolate-provider-boundary wagon implements it. Refs #1400.
"""RED skeleton for acc:isolate-provider-boundary:C001-UNIT-002-core-import-graph-provider-free.

wagon: isolate-provider-boundary | feature: enforce-import-boundary | phase: GREEN
WMBT: wmbt:isolate-provider-boundary:C001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the isolate-provider-boundary wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="isolate-provider-boundary not yet implemented (RED; #1400)")
def test_c001_unit_002_core_import_graph_provider_free(tmp_path) -> None:
    """C001-UNIT-002-core-import-graph-provider-free — behaviour not yet implemented."""
    raise AssertionError(
        "RED: isolate-provider-boundary acceptance acc:isolate-provider-boundary:C001-UNIT-002-core-import-graph-provider-free is not implemented yet"
    )
