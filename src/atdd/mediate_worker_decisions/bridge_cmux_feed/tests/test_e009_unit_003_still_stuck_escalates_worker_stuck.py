# URN: test:mediate-worker-decisions:bridge-cmux-feed:E009-UNIT-003-still-stuck-escalates-worker-stuck
# Acceptance: acc:mediate-worker-decisions:E009-UNIT-003-still-stuck-escalates-worker-stuck
# WMBT: wmbt:mediate-worker-decisions:E009
# Phase: RED
# Layer: application
# Assertion: behavioral
"""E009-UNIT-003 — a worker still parked after the fallback escalates worker_stuck.

When neither the reply nor the send-key fallback advances the worker (every check
False), the runner attempts the nudge and then returns an escalation outcome with
cause ``worker_stuck`` and NO verdict — never silently claiming the reply landed.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.bridge_cmux_feed.composition import build_feed_runner
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import (
    QUESTION,
    FeedItem,
)
from atdd.mediate_worker_decisions.bridge_cmux_feed.tests._helpers import (
    FakeCoach,
    FakeFeedTransport,
    FakeWorkerAdvance,
)
from atdd.mediate_worker_decisions.mediate_decision.src.domain.verdict import (
    CAUSE_WORKER_STUCK,
)


def _question_item() -> FeedItem:
    return FeedItem(
        id="i3",
        request_id="req-stuck",
        kind=QUESTION,
        question_prompt="Tabs or Spaces?",
        question_options=(
            {"id": "Alpha", "label": "Alpha", "description": ""},
            {"id": "Beta", "label": "Beta", "description": ""},
        ),
    )


def test_still_parked_after_fallback_escalates_worker_stuck():
    item = _question_item()
    advance = FakeWorkerAdvance(results=[False, False])  # never advances
    runner = build_feed_runner(
        source=None, reply=FakeFeedTransport(), coach=FakeCoach(), advance=advance
    )

    outcome = runner.handle(item)

    assert advance.nudge_calls == ["req-stuck"]  # fallback was attempted
    assert outcome.verdict is None               # never claim delivered
    assert outcome.escalation is not None
    assert outcome.escalation.cause == CAUSE_WORKER_STUCK
    assert outcome.escalation.request_id == "req-stuck"
