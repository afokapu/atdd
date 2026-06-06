# URN: test:mediate-worker-decisions:bridge-cmux-feed:E009-UNIT-001-verified-advance-no-fallback
# Acceptance: acc:mediate-worker-decisions:E009-UNIT-001-verified-advance-no-fallback
# WMBT: wmbt:mediate-worker-decisions:E009
# Phase: RED
# Layer: application
# Assertion: behavioral
"""E009-UNIT-001 — a reply that verifies the worker advanced needs no fallback.

When ``WorkerAdvance.confirm_advanced`` returns True on the first (post-reply)
check, the runner returns the verdict outcome, never issues a send-key nudge, and
never escalates.
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


def _question_item() -> FeedItem:
    return FeedItem(
        id="i1",
        request_id="req-q",
        kind=QUESTION,
        question_prompt="Tabs or Spaces?",
        question_options=(
            {"id": "Alpha", "label": "Alpha", "description": ""},
            {"id": "Beta", "label": "Beta", "description": ""},
        ),
    )


def test_verified_advance_returns_verdict_without_fallback():
    item = _question_item()
    transport = FakeFeedTransport()
    advance = FakeWorkerAdvance(results=[True])  # advanced on first check
    runner = build_feed_runner(
        source=None, reply=transport, coach=FakeCoach(), advance=advance
    )

    outcome = runner.handle(item)

    assert outcome.verdict is not None
    assert outcome.escalation is None
    assert advance.confirm_calls == 1  # verified once
    assert advance.nudge_calls == []   # no send-key fallback
    assert len(transport.calls) == 1   # reply delivered exactly once
