# URN: test:mediate-worker-decisions:coach-answer-escalation:L008-UNIT-002-status-omits-answered-escalations
# Acceptance: acc:mediate-worker-decisions:L008-UNIT-002-status-omits-answered-escalations
# WMBT: wmbt:mediate-worker-decisions:L008
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""L008-UNIT-002 — an answered escalation is omitted; only the unanswered remain.

Two escalation records, but only one request_id is still pending in the Feed; the
other has been answered (resolved / no longer pending) and must be omitted from
the listing.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import (
    QUESTION,
    FeedItem,
)
from atdd.mediate_worker_decisions.coach_answer_escalation.src.domain.escalation_surfacing import (
    list_unanswered_escalations,
)


def test_omits_the_answered_request_id():
    escalations = [
        {"escalation_id": "e1", "request_id": "req-answered", "cause": "operator_reserved"},
        {"escalation_id": "e2", "request_id": "req-open", "cause": "operator_reserved"},
    ]
    # only req-open is still pending — req-answered has been resolved
    pending = [
        FeedItem(
            id="i-open",
            request_id="req-open",
            kind=QUESTION,
            question_prompt="Still waiting",
            question_options=({"id": "o1", "label": "Yes"},),
        ),
    ]

    result = list_unanswered_escalations(escalations, pending)

    request_ids = [u.request_id for u in result]
    assert request_ids == ["req-open"]
    assert "req-answered" not in request_ids
