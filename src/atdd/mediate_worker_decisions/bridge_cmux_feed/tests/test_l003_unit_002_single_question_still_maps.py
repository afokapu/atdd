# URN: test:mediate-worker-decisions:bridge-cmux-feed:L003-UNIT-002-single-question-still-maps
# Acceptance: acc:mediate-worker-decisions:L003-UNIT-002-single-question-still-maps
# WMBT: wmbt:mediate-worker-decisions:L003
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""L003-UNIT-002 — a legacy single-question item still maps to a one-block document.

A feed item carrying only the top-level question_prompt/question_options mirror
(no questions[]) must still produce a one-block document (a single_choice block)
so the new document path is back-compatible with single-question agents.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import FeedItem
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item_mapper import (
    map_feed_item,
)
from atdd.mediate_worker_decisions.sense_decision.src.domain.decision_document import (
    SINGLE_CHOICE,
)


def test_single_question_mirror_maps_to_one_block():
    item = FeedItem(
        id="f1",
        request_id="req-q",
        kind="question",
        question_prompt="Which approach?",
        question_options=(
            {"id": "o0", "label": "Alpha", "description": ""},
            {"id": "o1", "label": "Beta", "description": ""},
        ),
    )

    req = map_feed_item(item)

    assert req.document is not None
    assert len(req.document.blocks) == 1
    block = req.document.blocks[0]
    assert block.kind == SINGLE_CHOICE
    assert [o.id for o in block.options] == ["o0", "o1"]
    assert [o.label for o in block.options] == ["Alpha", "Beta"]
