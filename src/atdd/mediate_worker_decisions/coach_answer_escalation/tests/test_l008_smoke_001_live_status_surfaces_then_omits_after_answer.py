# URN: test:mediate-worker-decisions:coach-answer-escalation:L008-SMOKE-001-live-status-surfaces-then-omits-after-answer
# Acceptance: acc:mediate-worker-decisions:L008-SMOKE-001-live-status-surfaces-then-omits-after-answer
# WMBT: wmbt:mediate-worker-decisions:L008
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""L008-SMOKE-001 — status surfaces a real escalation, then omits it once answered.

After a real managed feed_daemon escalates a live worker's decision into
``escalations.jsonl``, ``atdd coach status`` lists the unanswered request_id with
its prompt/options; after ``atdd coach answer`` resolves it, ``atdd coach status``
no longer lists it. In RED the harness is unimplemented so this fails.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.coach_answer_escalation.live_smoke import (
    status_surfaces_then_omits_live_smoke,
)


def test_l008_smoke_001_live_status_surfaces_then_omits_after_answer():
    evidence = status_surfaces_then_omits_live_smoke()

    assert evidence["listed_before_answer"] is True   # unanswered request_id surfaced
    assert evidence["omitted_after_answer"] is True    # omitted once resolved
