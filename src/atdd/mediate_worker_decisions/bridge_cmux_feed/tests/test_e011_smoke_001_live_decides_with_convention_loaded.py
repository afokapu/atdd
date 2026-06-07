# URN: test:mediate-worker-decisions:bridge-cmux-feed:E011-SMOKE-001-live-decides-with-convention-loaded
# Acceptance: acc:mediate-worker-decisions:E011-SMOKE-001-live-decides-with-convention-loaded
# WMBT: wmbt:mediate-worker-decisions:E011
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E011-SMOKE-001 — a live decider answers a real benign question with the convention loaded.

Drives the REAL bridge against a live cmux workspace whose worker is blocked on a
benign question, with the real ``LlmCoach`` carrying the repo coach convention
appended to its ``claude -p`` call. The harness records the convention text the
decider was actually handed (evidence per #983) and asserts BOTH: a verdict was
produced AND the coach convention was present in the decider's invocation.

Runs wherever cmux is on PATH; skips otherwise (the C003/E011 guarantees are
carried hermetically by the unit tests).
"""
from __future__ import annotations

import shutil

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("cmux") is None,
    reason="live cmux not available; run where the cmux CLI is installed",
)


def test_e011_smoke_001_live_decides_with_convention_loaded():
    from atdd.mediate_worker_decisions.bridge_cmux_feed.live_smoke import (
        decide_with_convention_live_smoke,
    )

    evidence = decide_with_convention_live_smoke()

    # a verdict was produced for the worker's benign question ...
    assert evidence["verdict_produced"] is True
    # ... AND the coach convention was present in the decider's claude -p call
    assert evidence["convention_present"] is True
