# URN: test:mediate-worker-decisions:feed-daemon:C004-SMOKE-001-live-dangerous-not-auto-answered
# Acceptance: acc:mediate-worker-decisions:C004-SMOKE-001-live-dangerous-not-auto-answered
# WMBT: wmbt:mediate-worker-decisions:C004
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C004-SMOKE-001 — a real agent's dangerous tool use is escalated by the daemon.

THE critical safety smoke. Drives the REAL daemon over one poll tick against a
live cmux workspace whose blocked permission requests a dangerous command: the
item must be recorded to the escalation ledger AND loud-logged, NO reply sent,
and the coach NEVER consulted.

The harness is real (verified by coach: it honestly raised PermissionNotInducible
rather than faking). The live condition is not inducible in this environment yet:
a non-auto worker blocks on the dangerous permission in its TUI, but that prompt
is never published to the cmux Feed (blocked count stays 0), so the daemon cannot
see it. That worker->Feed hook gap is tracked as #967. This becomes live once
#967 lands; the hermetic C004 unit+integration tests carry the safety guarantee
in the meantime.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason="requires worker→Feed hook wiring — spawned workers prompts not "
    "published to the Feed (#967); harness verified real by coach, condition "
    "not inducible until #967"
)


def test_c004_smoke_001_live_dangerous_not_auto_answered():
    from atdd.mediate_worker_decisions.bridge_cmux_feed.live_smoke import (
        PermissionNotInducible,
    )
    from atdd.mediate_worker_decisions.feed_daemon.live_smoke import (
        danger_escalates_live_smoke,
    )

    try:
        evidence = danger_escalates_live_smoke()
    except PermissionNotInducible:
        pytest.skip(
            "no blocked dangerous permission inducible under cmux auto-mode; "
            "the C004 unit+integration tests carry the safety guarantee"
        )

    # The headline safety property, proven end-to-end:
    assert evidence["auto_replied"] is False        # never auto-answered
    assert evidence["coach_consulted"] is False     # gate ran ahead of any LLM
    assert evidence["escalation_recorded"] is True  # durable human-channel record
    assert evidence["loud_logged"] is True          # operator-visible WARNING
    assert evidence["cause"] == "dangerous_action"
