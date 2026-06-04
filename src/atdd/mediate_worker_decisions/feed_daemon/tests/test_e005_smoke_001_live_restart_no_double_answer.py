# URN: test:mediate-worker-decisions:feed-daemon:E005-SMOKE-001-live-restart-no-double-answer
# Acceptance: acc:mediate-worker-decisions:E005-SMOKE-001-live-restart-no-double-answer
# WMBT: wmbt:mediate-worker-decisions:E005
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E005-SMOKE-001 — a restarted live daemon re-answers nothing.

Drives a REAL daemon over a dangerous (persistently blocked) item: after the
first daemon escalates it, a second daemon re-hydrating its answered-set from the
durable ledgers does NOT re-escalate it — no new ledger line, no reply, coach
untouched.

The harness is real. The live condition is not inducible in this environment yet:
the dangerous permission is not published to the cmux Feed (blocked count stays
0), so the daemon cannot see it — tracked as #967. Becomes live once #967 lands;
the hermetic E005 unit+integration tests carry the restart-idempotency guarantee.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason="requires worker→Feed hook wiring — spawned workers prompts not "
    "published to the Feed (#967); harness verified real by coach, condition "
    "not inducible until #967"
)


def test_e005_smoke_001_live_restart_no_double_answer():
    from atdd.mediate_worker_decisions.bridge_cmux_feed.live_smoke import (
        PermissionNotInducible,
    )
    from atdd.mediate_worker_decisions.feed_daemon.live_smoke import (
        restart_no_double_answer_live_smoke,
    )

    try:
        evidence = restart_no_double_answer_live_smoke()
    except PermissionNotInducible:
        pytest.skip(
            "no blocked dangerous permission inducible under cmux auto-mode; "
            "the E005 unit+integration tests carry the restart-idempotency guarantee"
        )

    assert evidence["re_answered"] is False
    assert evidence["escalation_lines_after"] == evidence["escalation_lines_before"]
