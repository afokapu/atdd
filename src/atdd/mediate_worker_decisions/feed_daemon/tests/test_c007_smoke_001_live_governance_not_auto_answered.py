# URN: test:mediate-worker-decisions:feed-daemon:C007-SMOKE-001-live-governance-question-not-auto-answered
# Acceptance: acc:mediate-worker-decisions:C007-SMOKE-001-live-governance-question-not-auto-answered
# WMBT: wmbt:mediate-worker-decisions:C007
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C007-SMOKE-001 — a real agent's phase sign-off is escalated by the daemon.

THE governance safety smoke, the direct counterpart of the wild bug: a live
worker raises a real "Approve → RED?" AskUserQuestion and the REAL daemon tick
must escalate it (cause=operator_reserved), deliver NO reply, record NO verdict,
and NEVER consult the coach. Unlike the dangerous case, a phase sign-off is a
normal blocking question so it IS inducible — when cmux + claude are on PATH
this runs end-to-end; otherwise it skips. The hermetic C007 unit+integration
tests carry the guarantee in CI where no live cmux exists.
"""
from __future__ import annotations

import shutil

import pytest


@pytest.mark.skipif(shutil.which("cmux") is None, reason="live cmux + claude not on PATH")
def test_c007_smoke_001_live_governance_not_auto_answered():
    from atdd.mediate_worker_decisions.feed_daemon.live_smoke import (
        governance_escalates_live_smoke,
    )

    evidence = governance_escalates_live_smoke()

    # The headline governance property, proven end-to-end on live substrate:
    assert evidence["auto_replied"] is False         # never auto-answered
    assert evidence["coach_consulted"] is False      # gate ran ahead of any LLM
    assert evidence["verdict_recorded"] is False      # no rubber-stamped verdict
    assert evidence["escalation_recorded"] is True    # durable human-channel record
    assert evidence["cause"] == "operator_reserved"
