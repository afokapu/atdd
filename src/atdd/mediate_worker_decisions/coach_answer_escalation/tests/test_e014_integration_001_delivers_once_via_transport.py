# URN: test:mediate-worker-decisions:coach-answer-escalation:E014-INTEGRATION-001-delivers-once-via-transport
# Acceptance: acc:mediate-worker-decisions:E014-INTEGRATION-001-delivers-once-via-transport
# WMBT: wmbt:mediate-worker-decisions:E014
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""E014-INTEGRATION-001 — ``atdd coach answer`` delivers through the transport once.

The use case looks the pending item up by request_id, plans the answer, and
delivers it via the FeedReplyApplier; the recording transport sees exactly one
``feed.question.reply`` call carrying the request_id and the exact-label selections.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import (
    QUESTION,
    FeedItem,
)
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.integration.feed_reply_applier import (
    FeedReplyApplier,
    InMemoryReplyGuard,
)
from atdd.mediate_worker_decisions.bridge_cmux_feed.tests._helpers import (
    FakeFeedSource,
    FakeFeedTransport,
)
from atdd.mediate_worker_decisions.coach_answer_escalation.src.application.answer_escalation import (
    AnswerEscalationUseCase,
)


def test_answer_delivers_exactly_once_with_params():
    item = FeedItem(
        id="i-3",
        request_id="req-q",
        kind=QUESTION,
        question_prompt="Pick a color",
        question_options=({"id": "o1", "label": "Blue"},),
    )
    transport = FakeFeedTransport()
    reply = FeedReplyApplier(transport=transport, guard=InMemoryReplyGuard())
    use_case = AnswerEscalationUseCase(source=FakeFeedSource([item]), reply=reply)

    use_case.answer("req-q", "Blue")

    assert len(transport.calls) == 1
    verb, params = transport.calls[0]
    assert verb == "feed.question.reply"
    assert params["request_id"] == "req-q"
    assert params["selections"] == ["Blue"]
