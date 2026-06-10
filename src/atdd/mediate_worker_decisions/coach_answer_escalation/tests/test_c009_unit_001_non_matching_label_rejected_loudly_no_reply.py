# URN: test:mediate-worker-decisions:coach-answer-escalation:C009-UNIT-001-non-matching-label-rejected-loudly-no-reply
# Acceptance: acc:mediate-worker-decisions:C009-UNIT-001-non-matching-label-rejected-loudly-no-reply
# WMBT: wmbt:mediate-worker-decisions:C009
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""C009-UNIT-001 — an input matching no option is rejected loudly, no reply built.

Resolving ``Green`` against options ``['Blue', 'Large']`` raises
``LabelResolutionError`` (loud), and planning the answer for the same mismatch
raises too — so no ``feed.question.reply`` is ever built or delivered.
"""
from __future__ import annotations

import pytest

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import (
    QUESTION,
    FeedItem,
)
from atdd.mediate_worker_decisions.bridge_cmux_feed.tests._helpers import (
    FakeFeedTransport,
)
from atdd.mediate_worker_decisions.coach_answer_escalation.src.application.answer_escalation import (
    plan_answer,
)
from atdd.mediate_worker_decisions.coach_answer_escalation.src.domain.label_resolver import (
    LabelResolutionError,
    resolve_exact_label,
)


def test_non_matching_label_raises_loudly():
    with pytest.raises(LabelResolutionError):
        resolve_exact_label("Green", ["Blue", "Large"])


def test_plan_answer_for_unknown_option_raises_and_sends_no_reply():
    item = FeedItem(
        id="i-c1",
        request_id="req-q",
        kind=QUESTION,
        question_prompt="Pick one",
        question_options=({"id": "o1", "label": "Blue"}, {"id": "o2", "label": "Large"}),
    )
    transport = FakeFeedTransport()

    with pytest.raises(LabelResolutionError):
        plan_answer(item, "Green")

    # the loud reject happens before any cmux reply — nothing was delivered
    assert transport.calls == []
