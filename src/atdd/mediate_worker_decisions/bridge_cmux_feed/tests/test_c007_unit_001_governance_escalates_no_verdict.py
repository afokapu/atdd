# URN: test:mediate-worker-decisions:bridge-cmux-feed:C007-UNIT-001-phase-sign-off-escalates-no-verdict
# Acceptance: acc:mediate-worker-decisions:C007-UNIT-001-phase-sign-off-escalates-no-verdict
# WMBT: wmbt:mediate-worker-decisions:C007
# Phase: RED
# Layer: application
# Assertion: behavioral
"""C007-UNIT-001 — a phase-transition sign-off escalates, no verdict, no coach.

The headline governance property: a worker's "Approve → RED?" phase sign-off is
operator-reserved. The runner classifies it BEFORE the coach is consulted and
escalates (cause=operator_reserved) — no verdict delivered, the coach mediate
brain never invoked, the transport reply verb never called.

RED state: handle() has no operator_reserved classification, so it falls through
to coach.mediate and auto-answers the governance question.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.bridge_cmux_feed.composition import build_feed_runner
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import FeedItem
from atdd.mediate_worker_decisions.bridge_cmux_feed.tests._helpers import (
    FakeCoach, FakeFeedSource, FakeFeedTransport,
)

GOVERNANCE_SIGN_OFF = FeedItem(
    id="f-gov",
    request_id="req-gov",
    kind="question",
    question_prompt="Approve → RED?",
    question_options=(
        {"id": "approve", "label": "Approve → RED", "description": ""},
        {"id": "hold", "label": "Hold in PLANNED", "description": ""},
    ),
)


def test_phase_sign_off_escalates_without_verdict_or_coach():
    transport = FakeFeedTransport()
    coach = FakeCoach()
    runner = build_feed_runner(
        source=FakeFeedSource([GOVERNANCE_SIGN_OFF]),
        reply=transport,
        coach=coach,
    )

    outcome = runner.handle(GOVERNANCE_SIGN_OFF)

    assert outcome.escalation is not None
    assert outcome.escalation.cause == "operator_reserved"
    assert outcome.escalation.safety_class == "operator_reserved"
    assert outcome.verdict is None          # never auto-answered
    assert coach.calls == []                # governance gate runs BEFORE the coach
    assert transport.calls == []            # no reply delivered for the sign-off
