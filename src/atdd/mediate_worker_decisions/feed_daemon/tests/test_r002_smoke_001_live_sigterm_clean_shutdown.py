# URN: test:mediate-worker-decisions:feed-daemon:R002-SMOKE-001-live-sigterm-clean-shutdown
# Acceptance: acc:mediate-worker-decisions:R002-SMOKE-001-live-sigterm-clean-shutdown
# WMBT: wmbt:mediate-worker-decisions:R002
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""R002-SMOKE-001 — a running daemon process exits cleanly on SIGTERM.

Spawns a REAL daemon process holding its pidfile lock, delivers SIGTERM, and
asserts the process exits and the lock is released. Opt-in via ATDD_LIVE_DAEMON=1
so it stays out of the default hermetic run.
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("ATDD_LIVE_DAEMON") != "1",
    reason="live daemon process smoke; set ATDD_LIVE_DAEMON=1 to run",
)


def test_r002_smoke_001_live_sigterm_clean_shutdown():
    from atdd.mediate_worker_decisions.feed_daemon.live_smoke import (
        sigterm_clean_shutdown_live_smoke,
    )

    evidence = sigterm_clean_shutdown_live_smoke()
    assert evidence["exited_cleanly"] is True
    assert evidence["lock_released"] is True
