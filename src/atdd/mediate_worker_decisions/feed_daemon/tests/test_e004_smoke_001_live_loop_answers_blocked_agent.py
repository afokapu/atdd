# URN: test:mediate-worker-decisions:feed-daemon:E004-SMOKE-001-live-loop-answers-blocked-agent
# Acceptance: acc:mediate-worker-decisions:E004-SMOKE-001-live-loop-answers-blocked-agent
# WMBT: wmbt:mediate-worker-decisions:E004
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E004-SMOKE-001 — a live daemon tick answers a real blocked agent.

Drives the REAL daemon over one poll tick against a live cmux workspace whose
worker is blocked on a decision; the item is answered and resolved.

The harness is real. The live condition is not inducible in this environment yet:
a spawned worker's prompt is not published to the cmux Feed (blocked count stays
0), so the daemon cannot see it — tracked as #967. Becomes live once #967 lands.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason="requires worker→Feed hook wiring — spawned workers prompts not "
    "published to the Feed (#967); harness verified real by coach, condition "
    "not inducible until #967"
)


def test_e004_smoke_001_live_loop_answers_blocked_agent():
    from atdd.mediate_worker_decisions.feed_daemon.live_smoke import (
        loop_answers_live_smoke,
    )

    evidence = loop_answers_live_smoke()
    assert evidence["resolved"] is True
