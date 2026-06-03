# URN: test:mediate-worker-decisions:apply-decision:E002-SMOKE-001-close-the-loop
# Acceptance: acc:mediate-worker-decisions:E002-SMOKE-001-close-the-loop
# WMBT: wmbt:mediate-worker-decisions:E002
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E002-SMOKE-001-close-the-loop — drive the REAL bridge against a REAL cmux
workspace: a worker prints a decision prompt, the coach answers, the answer is
delivered, and the worker reacts (loop closed). Runs whenever cmux is on PATH;
skips on runners without cmux. Drives the real entry points (no synthetic
fixture) per smoke.convention.
"""
from __future__ import annotations

import shutil

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("cmux") is None,
    reason="live cmux not available; run where the cmux CLI is installed",
)


def test_e002_smoke_001_close_the_loop():
    from atdd.mediate_worker_decisions.live_smoke import close_the_loop_smoke

    evidence = close_the_loop_smoke()
    # consumer_reacted: worker received the selected option and advanced
    assert evidence["disposition"] == "applied"
    # drift_resolved: the worker is past the prompt
    assert evidence["drift_resolved"] is True
