# URN: test:mediate-worker-decisions:feed-daemon:D002-SMOKE-001-live-second-instance-refused
# Acceptance: acc:mediate-worker-decisions:D002-SMOKE-001-live-second-instance-refused
# WMBT: wmbt:mediate-worker-decisions:D002
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""D002-SMOKE-001 — a second real daemon process refuses to start.

Spawns a REAL daemon holding the single-instance lock, then starts a second one
with the same lock path and asserts it refuses to start. Opt-in via
ATDD_LIVE_DAEMON=1 so it stays out of the default hermetic run.
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("ATDD_LIVE_DAEMON") != "1",
    reason="live daemon process smoke; set ATDD_LIVE_DAEMON=1 to run",
)


def test_d002_smoke_001_live_second_instance_refused():
    from atdd.mediate_worker_decisions.feed_daemon.live_smoke import (
        second_instance_refused_live_smoke,
    )

    evidence = second_instance_refused_live_smoke()
    assert evidence["second_refused"] is True
