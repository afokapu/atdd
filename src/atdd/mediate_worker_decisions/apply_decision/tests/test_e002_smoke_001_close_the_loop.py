# URN: test:mediate-worker-decisions:apply-decision:E002-SMOKE-001-close-the-loop
# Acceptance: acc:mediate-worker-decisions:E002-SMOKE-001-close-the-loop
# WMBT: wmbt:mediate-worker-decisions:E002
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E002-SMOKE-001-close-the-loop — live worker delivery / ledger (real agent_control + persistence)."""
from __future__ import annotations

import shutil

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("cmux") is None,
    reason="live cmux/agent runtime not available; run in a real session",
)


def test_e002_smoke_001_close_the_loop():
    from atdd.mediate_worker_decisions.apply_decision.composition import (
        build_apply_use_case_from_repo,
    )

    uc = build_apply_use_case_from_repo()
    assert uc is not None
    pytest.skip("requires a live blocked worker + agent runtime")
