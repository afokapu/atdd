# URN: test:mediate-worker-decisions:mediate-decision:C002-SMOKE-001-live-danger-escalates
# Acceptance: acc:mediate-worker-decisions:C002-SMOKE-001-live-danger-escalates
# WMBT: wmbt:mediate-worker-decisions:C002
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C002-SMOKE-001-live-danger-escalates — live cmux coach dialogue (real cmux)."""
from __future__ import annotations

import shutil

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("cmux") is None,
    reason="live cmux not available; run in a real cmux session",
)


def test_c002_smoke_001_live_danger_escalates():
    from atdd.mediate_worker_decisions.mediate_decision.composition import (
        build_mediate_use_case_from_repo,
    )

    uc = build_mediate_use_case_from_repo()
    assert uc is not None
    pytest.skip("requires a live cmux coach + worker session")
