# URN: test:mediate-worker-decisions:surface-worker-decisions:L004-SMOKE-001-live-worker-has-active-feed-hook
# Acceptance: acc:mediate-worker-decisions:L004-SMOKE-001-live-worker-has-active-feed-hook
# WMBT: wmbt:mediate-worker-decisions:L004
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""L004-SMOKE-001 — a live spawned worker has the Feed-publishing hook active.

Live end-to-end: a toolkit-spawned worker runs under the cmux wrapper with
CMUX_SURFACE_ID set, a live socket, and the injected --settings carrying the
PermissionRequest -> cmux hooks feed hook. The harness is real; runs at the SMOKE
phase after GREEN.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason="requires spawn-agents leash retirement + adapter wiring (#NEW); #967 "
    "lands the producer feature hermetic-only — goes live when that issue lands"
)


def test_l003_smoke_001_live_worker_has_active_feed_hook():
    from atdd.mediate_worker_decisions.surface_worker_decisions.live_smoke import (
        worker_has_active_feed_hook_live_smoke,
    )

    evidence = worker_has_active_feed_hook_live_smoke()
    assert evidence["surfaced"] is True
