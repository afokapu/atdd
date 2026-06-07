# URN: test:mediate-worker-decisions:coach-runtime:R003-SMOKE-001-live-stop-terminates-managed-daemon
# Acceptance: acc:mediate-worker-decisions:R003-SMOKE-001-live-stop-terminates-managed-daemon
# WMBT: wmbt:mediate-worker-decisions:R003
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""R003-SMOKE-001 — atdd coach stop terminates a real managed daemon.

Starts a REAL feed_daemon process via `atdd coach start` in a /tmp scratch dir,
then `atdd coach stop` and asserts the process exits and its pidfile is removed.
Skips cleanly when cmux is absent. Opt-in via ATDD_LIVE_DAEMON=1.
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("ATDD_LIVE_DAEMON") != "1",
    reason="live daemon process smoke; set ATDD_LIVE_DAEMON=1 to run",
)


def test_r003_smoke_001_live_stop_terminates_managed_daemon():
    from atdd.mediate_worker_decisions.coach_runtime.live_smoke import (
        stop_terminates_managed_daemon_live_smoke,
    )

    evidence = stop_terminates_managed_daemon_live_smoke()
    if evidence.get("skipped"):
        pytest.skip(evidence.get("reason", "cmux unavailable"))
    assert evidence["process_exited"] is True
    assert evidence["pidfile_removed"] is True
