# URN: test:mediate-worker-decisions:bridge-cmux-feed:E007-UNIT-001-reply-carries-per-question-selections
# Acceptance: acc:mediate-worker-decisions:E007-UNIT-001-reply-carries-per-question-selections
# WMBT: wmbt:mediate-worker-decisions:E007
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""E007-UNIT-001 — a multi-block verdict maps to flat selections for EVERY question.

cmux ``feed.question.reply`` takes a single flat ``selections: [label]`` list and
routes each label to its question by option membership. The reply mapper must
emit the chosen labels for EVERY block — the multi_choice question contributing
MULTIPLE labels — not a list carrying only the first question's selection (the
live bug).
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_reply_mapper import (
    plan_reply,
)
from atdd.mediate_worker_decisions.sense_decision.src.domain.decision_document import (
    MULTI_CHOICE,
    SINGLE_CHOICE,
    BlockAnswer,
    DecisionAnswer,
)
from atdd.mediate_worker_decisions.sense_decision.src.domain.decision_request import Option
from atdd.mediate_worker_decisions.mediate_decision.src.domain.verdict import (
    AUTO_APPLY,
    SOURCE_COACH,
    Verdict,
)


def _multi_block_verdict() -> Verdict:
    answer = DecisionAnswer(
        answers=(
            BlockAnswer("color", SINGLE_CHOICE, selected=(Option("blue", "Blue"),)),
            BlockAnswer("size", SINGLE_CHOICE, selected=(Option("m", "Medium"),)),
            BlockAnswer(
                "features", MULTI_CHOICE,
                selected=(Option("a", "Auth"), Option("c", "Cache")),
            ),
        )
    )
    return Verdict(
        verdict_id="v1",
        request_id="req-multi",
        decided_at="t",
        disposition=AUTO_APPLY,
        source=SOURCE_COACH,
        selected_option_id="Blue",
        reason="coach decided",
        answer=answer,
    )


def test_reply_carries_selections_for_every_question():
    plan = plan_reply(_multi_block_verdict(), kind="question")

    assert plan.verb == "feed.question.reply"
    assert plan.params["request_id"] == "req-multi"

    # one flat selections list covering EVERY question, in document order, with
    # the checkbox question contributing BOTH chosen labels — not just the first
    # question's selection.
    assert plan.params["selections"] == ["Blue", "Medium", "Auth", "Cache"]
