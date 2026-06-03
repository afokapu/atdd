# URN: test:mediate-worker-decisions:bridge-cmux-feed:C003-INTEGRATION-001-no-reply-for-dangerous
# Acceptance: acc:mediate-worker-decisions:C003-INTEGRATION-001-no-reply-for-dangerous
# WMBT: wmbt:mediate-worker-decisions:C003
# Phase: RED
# Layer: application
# Assertion: behavioral
"""C003-INTEGRATION-001 — a dangerous permission item is escalated, not replied.

The feed-driven runner handles a dangerous permission item (git push): an
escalation is emitted, the coach is never consulted, and the fake transport's
reply verb is never called.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.bridge_cmux_feed.composition import build_feed_runner
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import FeedItem
from atdd.mediate_worker_decisions.bridge_cmux_feed.tests._helpers import (
    FakeCoach, FakeFeedSource, FakeFeedTransport,
)


def test_dangerous_item_escalates_without_reply():
    item = FeedItem(
        id="f1",
        request_id="req-danger",
        kind="permission",
        question_prompt=None,
        question_options=(),
        tool_name="Bash",
        tool_input="git push origin main",
    )
    transport = FakeFeedTransport()
    coach = FakeCoach()
    runner = build_feed_runner(
        source=FakeFeedSource([item]),
        reply=transport,
        coach=coach,
    )

    outcome = runner.handle(item)

    assert outcome.escalation is not None
    assert outcome.escalation.cause == "dangerous_action"
    assert transport.calls == []   # no auto reply for a dangerous tool use
    assert coach.calls == []       # safety gate runs BEFORE the coach
