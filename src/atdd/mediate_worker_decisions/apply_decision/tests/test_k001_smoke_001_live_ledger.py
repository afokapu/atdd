# URN: test:mediate-worker-decisions:apply-decision:K001-SMOKE-001-live-ledger
# Acceptance: acc:mediate-worker-decisions:K001-SMOKE-001-live-ledger
# WMBT: wmbt:mediate-worker-decisions:K001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""K001-SMOKE-001-live-ledger — live worker delivery / ledger (real agent_control + persistence)."""
from __future__ import annotations

import shutil

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("cmux") is None,
    reason="live cmux/agent runtime not available; run in a real session",
)


def test_k001_smoke_001_live_ledger():
    from atdd.mediate_worker_decisions.apply_decision.composition import (
        build_apply_use_case_from_repo,
    )

    uc = build_apply_use_case_from_repo()
    assert uc is not None
    pytest.skip("requires a live blocked worker + agent runtime")
