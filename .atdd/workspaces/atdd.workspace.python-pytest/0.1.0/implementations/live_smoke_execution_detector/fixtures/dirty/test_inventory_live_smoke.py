# URN: test:demo:dirty:SMOKE-001-inventory-self-skips
# Acceptance: acc:demo:SMOKE-001-inventory-live
# execution_kind: live_smoke
# Phase: SMOKE
# Layer: integration
"""RED fixture: a live_smoke-anchored test that can SELF-SKIP. When the live
backend is absent it self-skips, so the acceptance passes vacuously without ever
executing against real infrastructure. The detector emits ONE raw self-skip
violation; under the strict disposition -> FAIL."""
import os

import pytest

pytestmark = [pytest.mark.platform]


def test_reserves_against_real_warehouse():
    if not os.environ.get("LIVE_WAREHOUSE_URL"):
        pytest.skip("live warehouse not configured")  # <- vacuous pass: never executes

    from app.inventory import Warehouse

    warehouse = Warehouse()
    assert warehouse.reserve("sku-1", 3).confirmed
