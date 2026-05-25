# URN: test:govern-lifecycle:smoke-false-green-prevention:E028-SMOKE-001-validate-planner-clean-after-retrofit
# Acceptance: acc:govern-lifecycle:E028-SMOKE-001-validate-planner-clean-after-retrofit
# WMBT: wmbt:govern-lifecycle:E028
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""
SMOKE: atdd validate planner --local --skip-api must exit 0 on the
post-retrofit repo with no planner.smoke.synthetic-fixture-bypass violations.
Currently fails (stub) — becomes SMOKE-ready after E029 retrofit commits the
real-spawn smoke tests and E028 GREEN wires the validator into the planner
suite.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.platform]


def test_validate_planner_clean_after_retrofit():
    """atdd validate planner --local --skip-api exits 0 on the post-retrofit repo."""
    pytest.fail(
        "SMOKE stub — run after E029 retrofit is committed and E028 validator is wired in. "
        "Expected: atdd validate planner --local --skip-api exits 0 with zero "
        "planner.smoke.synthetic-fixture-bypass violations."
    )
