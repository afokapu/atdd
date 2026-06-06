# URN: test:mediate-worker-decisions:bridge-cmux-feed:E009-UNIT-002-fallback-advances-stuck-worker
# Acceptance: acc:mediate-worker-decisions:E009-UNIT-002-fallback-advances-stuck-worker
# WMBT: wmbt:mediate-worker-decisions:E009
# Phase: RED
# Layer: application
# Assertion: behavioral
"""E009-UNIT-002 — a parked worker is advanced by the send-key fallback.

When the reply does not advance the worker (first check False), the runner issues
exactly one send-key nudge; a re-verify that then succeeds yields the verdict
outcome with no escalation.
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
        id="i2",
        request_id="req-stuck-then-ok",
        kind=QUESTION,
        question_prompt="Tabs or Spaces?",
        question_options=(
            {"id": "Alpha", "label": "Alpha", "description": ""},
            {"id": "Beta", "label": "Beta", "description": ""},
        ),
    )


def test_send_key_fallback_unblocks_parked_worker():
    item = _question_item()
    transport = FakeFeedTransport()
    # not advanced by the reply, then advanced after the nudge
    advance = FakeWorkerAdvance(results=[False, True])
    runner = build_feed_runner(
        source=None, reply=transport, coach=FakeCoach(), advance=advance
    )

    outcome = runner.handle(item)

    assert advance.nudge_calls == ["req-stuck-then-ok"]  # send-key issued once
    assert advance.confirm_calls == 2                     # verify + re-verify
    assert outcome.verdict is not None
    assert outcome.escalation is None
