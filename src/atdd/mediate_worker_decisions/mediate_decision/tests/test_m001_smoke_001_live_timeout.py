# URN: test:mediate-worker-decisions:mediate-decision:M001-SMOKE-001-live-timeout
# Acceptance: acc:mediate-worker-decisions:M001-SMOKE-001-live-timeout
# WMBT: wmbt:mediate-worker-decisions:M001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""M001-SMOKE-001-live-timeout — live cmux coach dialogue (real cmux)."""
from __future__ import annotations

import shutil

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("cmux") is None,
    reason="live cmux not available; run in a real cmux session",
)


def test_m001_smoke_001_live_timeout():
    from atdd.mediate_worker_decisions.mediate_decision.composition import (
        build_mediate_use_case_from_repo,
    )

    uc = build_mediate_use_case_from_repo()
    assert uc is not None
    pytest.skip("requires a live cmux coach + worker session")
