# URN: test:mediate-worker-decisions:coach-answer-escalation:E014-UNIT-002-question-reply-exact-label-selections
# Acceptance: acc:mediate-worker-decisions:E014-UNIT-002-question-reply-exact-label-selections
# WMBT: wmbt:mediate-worker-decisions:E014
# Phase: RED
# Layer: application
# Assertion: behavioral
"""E014-UNIT-002 — ``atdd coach answer`` on a question item carries the exact label.

The operator names the ``Blue`` option; the reply is ``feed.question.reply`` with
the request_id and ``selections == ['Blue']`` — the exact ``question_options[].label``,
not the raw operator string.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import (
    QUESTION,
    FeedItem,
)
from atdd.mediate_worker_decisions.coach_answer_escalation.src.application.answer_escalation import (
    plan_answer,
)


def _question_item() -> FeedItem:
    return FeedItem(
        id="i-2",
        request_id="req-q",
        kind=QUESTION,
        question_prompt="Pick a color",
        question_options=(
            {"id": "o1", "label": "Blue"},
            {"id": "o2", "label": "Red"},
        ),
    )


def test_question_answer_yields_exact_label_selections():
    plan = plan_answer(_question_item(), "Blue")

    assert plan.verb == "feed.question.reply"
    assert plan.params["request_id"] == "req-q"
    assert plan.params["selections"] == ["Blue"]
