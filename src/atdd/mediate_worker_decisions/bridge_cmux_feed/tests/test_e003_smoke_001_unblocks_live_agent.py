# URN: test:mediate-worker-decisions:bridge-cmux-feed:E003-SMOKE-001-unblocks-live-agent
# Acceptance: acc:mediate-worker-decisions:E003-SMOKE-001-unblocks-live-agent
# WMBT: wmbt:mediate-worker-decisions:E003
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E003-SMOKE-001 — a coach verdict replied via the Feed unblocks a real agent.

Drives the REAL bridge against a live cmux workspace: a worker blocked on a Feed
decision is unblocked end-to-end by delivering the coach verdict via feed reply,
and proceeds with the chosen option. Runs whenever cmux is on PATH; skips on
runners without cmux.
"""
from __future__ import annotations

import shutil

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("cmux") is None,
    reason="live cmux not available; run where the cmux CLI is installed",
)


def test_e003_smoke_001_unblocks_live_agent():
    from atdd.mediate_worker_decisions.bridge_cmux_feed.live_smoke import unblock_live_smoke

    evidence = unblock_live_smoke()
    assert evidence["resolved"] is True
