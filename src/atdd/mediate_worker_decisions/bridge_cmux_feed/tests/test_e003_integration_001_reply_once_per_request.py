# URN: test:mediate-worker-decisions:bridge-cmux-feed:E003-INTEGRATION-001-reply-once-per-request
# Acceptance: acc:mediate-worker-decisions:E003-INTEGRATION-001-reply-once-per-request
# WMBT: wmbt:mediate-worker-decisions:E003
# Phase: RED
# Layer: application
# Assertion: behavioral
"""E003-INTEGRATION-001 — the same request_id is replied to exactly once.

Delivering the same reply plan twice through the applier (with an idempotency
guard) results in the fake transport's reply verb being called exactly once.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.bridge_cmux_feed.composition import (
    build_feed_reply_applier,
)
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import (
    FeedReplyPlan,
)
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.integration.feed_reply_applier import (
    InMemoryReplyGuard,
)
from atdd.mediate_worker_decisions.bridge_cmux_feed.tests._helpers import FakeFeedTransport


def test_reply_delivered_exactly_once():
    transport = FakeFeedTransport()
    applier = build_feed_reply_applier(transport=transport, guard=InMemoryReplyGuard())
    plan = FeedReplyPlan(
        verb="feed.question.reply",
        params={"request_id": "req-1", "selections": ["Alpha"]},
    )

    applier.deliver(plan)
    applier.deliver(plan)  # replay same request_id

    assert len(transport.calls) == 1
    assert transport.calls[0][0] == "feed.question.reply"
    assert transport.calls[0][1]["request_id"] == "req-1"
