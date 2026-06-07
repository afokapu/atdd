# URN: test:mediate-worker-decisions:coach-runtime:E010-SMOKE-001-live-start-launches-scoped-daemon
# Acceptance: acc:mediate-worker-decisions:E010-SMOKE-001-live-start-launches-scoped-daemon
# WMBT: wmbt:mediate-worker-decisions:E010
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E010-SMOKE-001 — atdd coach start launches the scoped feed_daemon for real.

Runs the REAL start path in a /tmp scratch runtime dir: it spawns the actual
feed_daemon CLI subprocess scoped to a workspace and asserts a manager pidfile
is written naming a live process. Skips cleanly when cmux is absent. Opt-in via
ATDD_LIVE_DAEMON=1 so it stays out of the default hermetic run.
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("ATDD_LIVE_DAEMON") != "1",
    reason="live daemon process smoke; set ATDD_LIVE_DAEMON=1 to run",
)


def test_e010_smoke_001_live_start_launches_scoped_daemon():
    from atdd.mediate_worker_decisions.coach_runtime.live_smoke import (
        start_launches_scoped_daemon_live_smoke,
    )

    evidence = start_launches_scoped_daemon_live_smoke()
    if evidence.get("skipped"):
        pytest.skip(evidence.get("reason", "cmux unavailable"))
    assert evidence["pidfile_written"] is True
    assert evidence["process_alive"] is True
