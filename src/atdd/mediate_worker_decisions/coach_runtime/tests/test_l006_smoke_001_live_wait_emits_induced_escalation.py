# URN: test:mediate-worker-decisions:coach-runtime:L006-SMOKE-001-live-wait-emits-induced-escalation
# Acceptance: acc:mediate-worker-decisions:L006-SMOKE-001-live-wait-emits-induced-escalation
# WMBT: wmbt:mediate-worker-decisions:L006
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""L006-SMOKE-001 — atdd coach wait emits exactly the induced escalation.

Starts a managed daemon on a real worker workspace, induces an escalation
(worker_stuck, or a now-surfaced dangerous decision via #971), and asserts
`atdd coach wait` prints exactly that escalation record then exits — and a
second wait does not re-emit it. Skips cleanly when cmux is absent. Opt-in via
ATDD_LIVE_DAEMON=1.
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("ATDD_LIVE_DAEMON") != "1",
    reason="live daemon process smoke; set ATDD_LIVE_DAEMON=1 to run",
)


def test_l006_smoke_001_live_wait_emits_induced_escalation():
    from atdd.mediate_worker_decisions.coach_runtime.live_smoke import (
        wait_emits_induced_escalation_live_smoke,
    )

    evidence = wait_emits_induced_escalation_live_smoke()
    if evidence.get("skipped"):
        pytest.skip(evidence.get("reason", "cmux/worker unavailable"))
    assert evidence["emitted_escalation_id"] == evidence["induced_escalation_id"]
    assert evidence["reemitted"] is False  # cursor advanced; not surfaced twice
