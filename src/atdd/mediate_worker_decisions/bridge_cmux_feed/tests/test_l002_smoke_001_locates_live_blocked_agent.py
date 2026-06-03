# URN: test:mediate-worker-decisions:bridge-cmux-feed:L002-SMOKE-001-locates-live-blocked-agent
# Acceptance: acc:mediate-worker-decisions:L002-SMOKE-001-locates-live-blocked-agent
# WMBT: wmbt:mediate-worker-decisions:L002
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""L002-SMOKE-001 — a real agent's live blocked decision is located from the Feed.

Drives the REAL feed event source against a live cmux workspace whose worker has
called AskUserQuestion and is blocked pending. A request must be produced
carrying the live request_id and the agent's options. Runs whenever cmux is on
PATH; skips on runners without cmux.
"""
from __future__ import annotations

import shutil

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("cmux") is None,
    reason="live cmux not available; run where the cmux CLI is installed",
)


def test_l002_smoke_001_locates_live_blocked_agent():
    from atdd.mediate_worker_decisions.bridge_cmux_feed.live_smoke import locate_live_smoke

    evidence = locate_live_smoke()
    assert evidence["request_id"]
    assert evidence["options"]
