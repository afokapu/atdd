# URN: test:spawn-agents:coach-spawn-respawn-reliability-primitives:M003-SMOKE-001-real-hung-warm-resume-times-out
# Acceptance: acc:spawn-agents:M003-SMOKE-001-real-hung-warm-resume-times-out
# WMBT: wmbt:spawn-agents:M003
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""M003-SMOKE-001 — on real infrastructure a genuinely hung warm-resume times out
within the budget and writes an escalation (rescues the orchestrator from an
indefinite stall).

Live-on-demand. Skips in CI / when not opted in (ATDD_RUN_SMOKE=1). In RED the
live-smoke harness is unimplemented → skipped.
"""
from __future__ import annotations

import os

import pytest

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        os.environ.get("ATDD_RUN_SMOKE") != "1",
        reason="live warm-resume timeout smoke — opt in with ATDD_RUN_SMOKE=1",
    ),
]


def test_real_hung_warm_resume_times_out():
    from atdd.train.warm_resume_watchdog.live_smoke import (  # noqa: WPS433
        hung_warm_resume_times_out_live_smoke,
    )

    evidence = hung_warm_resume_times_out_live_smoke()

    assert evidence["returned_within_budget"] is True, "must return ~budget, not block forever"
    assert evidence["escalation_written"] is True, "an escalation line names issue + transition"
    assert evidence["zombie_spawn_left"] is False, "no zombie spawn after the timeout"
