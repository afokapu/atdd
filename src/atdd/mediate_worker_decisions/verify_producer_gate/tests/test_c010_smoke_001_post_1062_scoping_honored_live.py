# URN: test:mediate-worker-decisions:verify-producer-gate:C010-SMOKE-001-post-1062-scoping-honored-live
# Acceptance: acc:mediate-worker-decisions:C010-SMOKE-001-post-1062-scoping-honored-live
# WMBT: wmbt:mediate-worker-decisions:C010
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C010-SMOKE-001 — post-#1062 scoping is honored live.

Live end-to-end over the real cmux Feed and a real post-#1062 worker: a freedom-layer
safe command (``pytest --version``) auto-runs with NO Feed item while a gated command
(``git push --dry-run``) publishes a ``permissionRequest``. The headline live proof the
empirical anchor (all pre-#1062) left open — that Claude Code honors the comma-delimited
scoped allow-list at runtime. Skips cleanly in CI / when not opted in (ATDD_LIVE_SMOKE=1).
"""
from __future__ import annotations

import pytest

from atdd.mediate_worker_decisions.verify_producer_gate.live_smoke import (
    live_smoke_available,
    scoping_honored_live_smoke,
)


def test_c010_smoke_001_post_1062_scoping_honored_live():
    skip = live_smoke_available()
    if skip:
        pytest.skip(skip)
    evidence = scoping_honored_live_smoke()
    # The safe command auto-ran: it never reached the Feed.
    assert evidence["safe_surfaced"] is False
    # The gated command surfaced a permissionRequest for the daemon to mediate.
    assert evidence["gated_surfaced"] is True
