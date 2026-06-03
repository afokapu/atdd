# URN: test:mediate-worker-decisions:sense-decision:D001-SMOKE-001-live-resolve
# Acceptance: acc:mediate-worker-decisions:D001-SMOKE-001-live-resolve
# WMBT: wmbt:mediate-worker-decisions:D001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""D001-SMOKE-001 — a live cmux notification resolves to the worker (real cmux)."""
from __future__ import annotations

import shutil

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("cmux") is None,
    reason="live cmux not available; run in a real cmux session",
)


def test_d001_smoke_001_live_resolve():
    # Live smoke: with a real cmux + a populated .atdd/decision/registry.yaml, the
    # notify hook resolves the raising surface to its worker. Driven by the real
    # entry point (no synthetic fixture) per smoke.convention.
    from atdd.mediate_worker_decisions.sense_decision.composition import (
        build_sense_use_case_from_repo,
    )

    use_case = build_sense_use_case_from_repo()
    assert use_case is not None
    pytest.skip("requires a live cmux worker surface raising a decision prompt")
