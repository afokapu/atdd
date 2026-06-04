# URN: test:mediate-worker-decisions:surface-worker-decisions:E006-SMOKE-001-live-spawned-worker-decision-appears-blocked-in-feed
# Acceptance: acc:mediate-worker-decisions:E006-SMOKE-001-live-spawned-worker-decision-appears-blocked-in-feed
# WMBT: wmbt:mediate-worker-decisions:E006
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E006-SMOKE-001 — a toolkit-spawned worker's blocking decision appears in feed.list.

Live end-to-end over the real cmux Feed and a real toolkit-spawned worker — the
headline proof of #967. The harness is real; it runs at the SMOKE phase once GREEN
wires the spawn path to apply the DecisionSurfacingPolicy. Producing a status
blocked item here is what lets the coach start feed_daemon and unblocks the
daemon's skip-marked C004/E004/E005 live smokes (#966).
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason="requires spawn-agents leash retirement + adapter wiring (#NEW); #967 "
    "lands the producer feature hermetic-only — goes live when that issue lands"
)


def test_e006_smoke_001_live_spawned_worker_decision_appears_blocked_in_feed():
    from atdd.mediate_worker_decisions.surface_worker_decisions.live_smoke import (
        decision_appears_blocked_live_smoke,
    )

    evidence = decision_appears_blocked_live_smoke()
    assert evidence["surfaced"] is True
