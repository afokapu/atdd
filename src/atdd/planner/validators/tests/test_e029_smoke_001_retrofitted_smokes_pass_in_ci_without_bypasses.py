# URN: test:govern-lifecycle:smoke-false-green-prevention:E029-SMOKE-001-retrofitted-smokes-pass-in-ci-without-bypasses
# Acceptance: acc:govern-lifecycle:E029-SMOKE-001-retrofitted-smokes-pass-in-ci-without-bypasses
# WMBT: wmbt:govern-lifecycle:E029
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""
SMOKE: Retrofitted E003-SMOKE tests must pass in CI with no bypass env vars
(no ATDD_RUN_SMOKE, ATDD_SKIP_*, or other overrides).  Currently fails (stub)
— becomes SMOKE-ready after E029 GREEN phase commits the real-spawn test bodies
and CI confirms they pass without any bypass flags.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.platform]


def test_retrofitted_smokes_pass_in_ci_without_bypasses():
    """E003-SMOKE-001, E003-SMOKE-002, E004-SMOKE-001 all pass in CI with no bypass env vars."""
    pytest.fail(
        "SMOKE stub — run after E029 retrofit is merged and CI confirms the tests pass. "
        "Expected: test_e003_smoke_001, test_e003_smoke_002, test_e004_smoke_001 all "
        "collect and pass without ATDD_RUN_SMOKE=1 or any bypass env vars in CI."
    )
