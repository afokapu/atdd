# URN: test:govern-lifecycle:smoke-false-green-prevention:E029-INTEGRATION-001-retrofitted-smoke-tests-pass
# Acceptance: acc:govern-lifecycle:E029-INTEGRATION-001-retrofitted-smoke-tests-pass
# WMBT: wmbt:govern-lifecycle:E029
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""
GREEN: Both retrofitted E003-SMOKE tests must execute and pass using real
atdd spawn wiring without ATDD_RUN_SMOKE set.  Currently fails (stub) —
becomes GREEN once test_e003_smoke_001 and test_e003_smoke_002 are rewritten
to use real atdd spawn invocations.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.planner]


def test_retrofitted_smoke_tests_pass():
    """Both E003-SMOKE tests must pass with real spawn wiring — no ATDD_RUN_SMOKE bypass."""
    pytest.fail(
        "GREEN stub — implement after E029 retrofit commits the real-spawn test bodies. "
        "Expected: pytest targeting test_e003_smoke_001 and test_e003_smoke_002 passes "
        "without ATDD_RUN_SMOKE=1 or any synthetic-fixture bypass env vars."
    )
