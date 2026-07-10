# URN: test:reconcile-local-store:hydrate-cold-store:P002-SMOKE-001-cold-start-hydrate
# Acceptance: acc:reconcile-local-store:P002-SMOKE-001-cold-start-hydrate
# WMBT: wmbt:reconcile-local-store:P002
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:reconcile-local-store:P002-SMOKE-001-cold-start-hydrate — fails until the reconcile-local-store wagon implements it (train 0006). Refs #1400.
"""RED skeleton for acc:reconcile-local-store:P002-SMOKE-001-cold-start-hydrate.

wagon: reconcile-local-store | feature: hydrate-cold-store | phase: RED
WMBT: wmbt:reconcile-local-store:P002

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the reconcile-local-store wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.smoke
@pytest.mark.xfail(strict=True, reason="reconcile-local-store not yet implemented (RED; #1400)")
def test_p002_smoke_001_cold_start_hydrate(tmp_path) -> None:
    """P002-SMOKE-001-cold-start-hydrate — behaviour not yet implemented."""
    raise AssertionError(
        "RED: reconcile-local-store acceptance acc:reconcile-local-store:P002-SMOKE-001-cold-start-hydrate is not implemented yet"
    )
