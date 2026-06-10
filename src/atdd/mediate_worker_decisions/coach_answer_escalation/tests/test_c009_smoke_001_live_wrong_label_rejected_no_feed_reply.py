# URN: test:mediate-worker-decisions:coach-answer-escalation:C009-SMOKE-001-live-wrong-label-rejected-no-feed-reply
# Acceptance: acc:mediate-worker-decisions:C009-SMOKE-001-live-wrong-label-rejected-no-feed-reply
# WMBT: wmbt:mediate-worker-decisions:C009
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C009-SMOKE-001 — against a live worker, a wrong label is rejected, no reply sent.

The operator runs ``atdd coach answer`` with a label that does not exactly match
any option on a real parked AskUserQuestion: the command exits loudly and NO feed
reply is delivered (no false ``delivered:true``), so the worker stays parked. In
RED the harness is unimplemented so this fails.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.coach_answer_escalation.live_smoke import (
    wrong_label_rejected_live_smoke,
)


def test_c009_smoke_001_live_wrong_label_rejected_no_feed_reply():
    evidence = wrong_label_rejected_live_smoke()

    assert evidence["rejected_loudly"] is True      # non-zero exit naming input + options
    assert evidence["reply_delivered"] is False     # no cmux reply, no false delivered:true
    assert evidence["worker_still_parked"] is True  # worker awaits a correct answer
