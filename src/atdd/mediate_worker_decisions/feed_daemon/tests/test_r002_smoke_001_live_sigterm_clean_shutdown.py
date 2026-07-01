# URN: test:mediate-worker-decisions:feed-daemon:R002-SMOKE-001-live-sigterm-clean-shutdown
# Acceptance: acc:mediate-worker-decisions:R002-SMOKE-001-live-sigterm-clean-shutdown
# WMBT: wmbt:mediate-worker-decisions:R002
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""R002-SMOKE-001 — a running daemon process exits cleanly on SIGTERM.

Spawns a REAL daemon process holding its pidfile lock, delivers SIGTERM, and
asserts the process exits and the lock is released. Runs unconditionally: this
smoke needs only a Python interpreter (no cmux/claude), so it runs-or-fails in
every lane rather than self-skipping into a vacuous pass (#1151, #1298).
"""
from __future__ import annotations


def test_r002_smoke_001_live_sigterm_clean_shutdown():
    from atdd.mediate_worker_decisions.feed_daemon.live_smoke import (
        sigterm_clean_shutdown_live_smoke,
    )

    evidence = sigterm_clean_shutdown_live_smoke()
    assert evidence["exited_cleanly"] is True
    assert evidence["lock_released"] is True
