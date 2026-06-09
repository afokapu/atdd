# URN: test:mediate-worker-decisions:surface-worker-decisions:E013-SMOKE-001-dispatch-worker-decision-publishes-to-feed
# Acceptance: acc:mediate-worker-decisions:E013-SMOKE-001-dispatch-worker-decision-publishes-to-feed
# WMBT: wmbt:mediate-worker-decisions:E013
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E013-SMOKE-001 — a dispatch-spawned worker's decision publishes to the Feed.

A worker spawned through the REAL dispatch worker-spawn path (own-workspace
foreground launch) raises a gated Bash decision that appears in
``cmux rpc feed.list`` — proving the wrapper Feed hook is live for the dispatch
spawn, not just for the standalone live-smoke spawn. This is the producer half
the closed #967 missed for the dispatch path.

Opt-in (needs live cmux + claude); skips cleanly otherwise. Evidence recorded in
docs/smoke-audit.md by the coach."""
from __future__ import annotations

import pytest


def test_e013_smoke_001_dispatch_worker_decision_publishes_to_feed():
    from atdd.mediate_worker_decisions.surface_worker_decisions.live_smoke import (
        dispatch_worker_decision_publishes_live_smoke,
        live_smoke_available,
    )

    skip = live_smoke_available()
    if skip:
        pytest.skip(skip)

    result = dispatch_worker_decision_publishes_live_smoke()

    assert result["surfaced"] is True, (
        f"dispatch-spawned worker published nothing to feed.list — hook path not "
        f"live for the dispatch spawn; saw: {result.get('evidence')!r}"
    )
