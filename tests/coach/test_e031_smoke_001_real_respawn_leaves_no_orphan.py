# URN: test:spawn-agents:coach-spawn-respawn-reliability-primitives:E031-SMOKE-001-real-respawn-leaves-no-orphan
# Acceptance: acc:spawn-agents:E031-SMOKE-001-real-respawn-leaves-no-orphan
# WMBT: wmbt:spawn-agents:E031
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E031-SMOKE-001 — on real infrastructure the kill-before-respawn path removes
the prior worker process, leaving exactly one fresh process and no orphan/ghost.

Live-on-demand: runs a real worker under a real multiplexer backend. Skips
cleanly in CI / when not opted in (ATDD_RUN_SMOKE=1). In RED the live-smoke
harness is unimplemented so this is skipped, not green.
"""
from __future__ import annotations

import os

import pytest

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        os.environ.get("ATDD_RUN_SMOKE") != "1",
        reason="live respawn smoke — opt in with ATDD_RUN_SMOKE=1",
    ),
]


def test_real_respawn_leaves_no_orphan():
    from atdd.coach.respawn_guards.live_smoke import (  # noqa: WPS433
        respawn_leaves_no_orphan_live_smoke,
    )

    evidence = respawn_leaves_no_orphan_live_smoke()

    assert evidence["prior_pid_running"] is False, "prior worker PID must be gone"
    assert evidence["fresh_worker_count"] == 1, "exactly one fresh worker on the surface"
    assert evidence["orphans"] == [], "no detached/orphan process left behind"
