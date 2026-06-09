# URN: test:mediate-worker-decisions:bridge-cmux-feed:C007-UNIT-002-routine-design-question-still-auto-answered
# Acceptance: acc:mediate-worker-decisions:C007-UNIT-002-routine-design-question-still-auto-answered
# WMBT: wmbt:mediate-worker-decisions:C007
# Phase: RED
# Layer: application
# Assertion: behavioral
"""C007-UNIT-002 — a routine design-preference question is still auto-answered.

No regression of the working path: a design-preference AskUserQuestion with no
phase-sign-off / governance markers is NOT operator_reserved — the coach IS
consulted and an auto_apply verdict is delivered. Only governance escalates.

RED state: introducing the operator_reserved classifier must not capture routine
questions; this test pins the no-regression boundary.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.bridge_cmux_feed.composition import build_feed_runner
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import FeedItem
from atdd.mediate_worker_decisions.bridge_cmux_feed.tests._helpers import (
    FakeCoach, FakeFeedSource, FakeFeedTransport,
)

ROUTINE_DESIGN_QUESTION = FeedItem(
    id="f-color",
    request_id="req-color",
    kind="question",
    question_prompt="Which colour for the primary button?",
    question_options=(
        {"id": "blue", "label": "Blue", "description": ""},
        {"id": "red", "label": "Red", "description": ""},
    ),
)


def test_routine_design_question_is_auto_answered():
    transport = FakeFeedTransport()
    coach = FakeCoach()
    runner = build_feed_runner(
        source=FakeFeedSource([ROUTINE_DESIGN_QUESTION]),
        reply=transport,
        coach=coach,
    )

    outcome = runner.handle(ROUTINE_DESIGN_QUESTION)

    assert outcome.verdict is not None                 # auto-answered as before
    assert coach.calls != []                           # the coach decided it
    assert outcome.escalation is None                  # no governance escalation
    assert any(v == "feed.question.reply" for v, _ in transport.calls)
