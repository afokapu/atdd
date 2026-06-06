# URN: test:mediate-worker-decisions:surface-worker-decisions:E008-SMOKE-001-live-spawned-worker-decision-appears-blocked-in-feed
# Acceptance: acc:mediate-worker-decisions:E008-SMOKE-001-live-spawned-worker-decision-appears-blocked-in-feed
# WMBT: wmbt:mediate-worker-decisions:E008
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E008-SMOKE-001 — a toolkit-spawned worker's blocking decision appears in feed.list.

Live end-to-end over the real cmux Feed and a real toolkit-spawned worker — the
headline proof of #967. The harness is real; it runs at the SMOKE phase once GREEN
wires the spawn path to apply the DecisionSurfacingPolicy. Producing a status
blocked item here is what lets the coach start feed_daemon and unblocks the
daemon's skip-marked C004/E004/E005 live smokes (#966).
"""
from __future__ import annotations

import pytest

from atdd.mediate_worker_decisions.surface_worker_decisions.live_smoke import (
    decision_appears_blocked_live_smoke,
    live_smoke_available,
)


def test_e008_smoke_001_live_spawned_worker_decision_appears_blocked_in_feed():
    # Live-on-demand: spawns a real worker under cmux. Skips cleanly in CI / when
    # not opted in (ATDD_LIVE_SMOKE=1). Documented run: docs/smoke-audit.md (#971).
    skip = live_smoke_available()
    if skip:
        pytest.skip(skip)
    evidence = decision_appears_blocked_live_smoke()
    assert evidence["surfaced"] is True
    assert evidence["evidence"]["status"] == "pending"
