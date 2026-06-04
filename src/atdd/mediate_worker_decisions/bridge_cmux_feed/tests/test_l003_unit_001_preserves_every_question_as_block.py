# URN: test:mediate-worker-decisions:bridge-cmux-feed:L003-UNIT-001-preserves-every-question-as-block
# Acceptance: acc:mediate-worker-decisions:L003-UNIT-001-preserves-every-question-as-block
# WMBT: wmbt:mediate-worker-decisions:L003
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""L003-UNIT-001 — a multi-question feed item maps to a full block document.

The live bug: a worker emitted one AskUserQuestion with three questions
(Color / Size / Features-checkbox) and the mapper flattened to the first. The
mapper must instead preserve EVERY question as a block, in order, with the
multi_select question mapped to a multi_choice block — not dropped.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import FeedItem
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item_mapper import (
    map_feed_item,
)
from atdd.mediate_worker_decisions.sense_decision.src.domain.decision_document import (
    MULTI_CHOICE,
    SINGLE_CHOICE,
)


def _three_question_item() -> FeedItem:
    return FeedItem(
        id="f1",
        request_id="req-multi",
        kind="question",
        # top-level mirror is the FIRST question only — the old flatten source
        question_prompt="Pick a color",
        question_options=(
            {"id": "blue", "label": "Blue", "description": ""},
            {"id": "red", "label": "Red", "description": ""},
        ),
        questions=(
            {
                "id": "color",
                "header": "Color",
                "prompt": "Pick a color",
                "multi_select": False,
                "options": [
                    {"id": "blue", "label": "Blue"},
                    {"id": "red", "label": "Red"},
                ],
            },
            {
                "id": "size",
                "header": "Size",
                "prompt": "Pick a size",
                "multi_select": False,
                "options": [
                    {"id": "s", "label": "Small"},
                    {"id": "m", "label": "Medium"},
                ],
            },
            {
                "id": "features",
                "header": "Features",
                "prompt": "Pick the features",
                "multi_select": True,
                "options": [
                    {"id": "a", "label": "Auth"},
                    {"id": "b", "label": "Billing"},
                    {"id": "c", "label": "Cache"},
                ],
            },
        ),
    )


def test_every_question_preserved_in_order_as_blocks():
    req = map_feed_item(_three_question_item())

    doc = req.document
    assert doc is not None, "the multi-question item must map to a decision document"
    assert [b.block_id for b in doc.blocks] == ["color", "size", "features"]


def test_multi_select_question_maps_to_multi_choice_block():
    req = map_feed_item(_three_question_item())
    by_id = {b.block_id: b for b in req.document.blocks}

    assert by_id["color"].kind == SINGLE_CHOICE
    assert by_id["size"].kind == SINGLE_CHOICE
    assert by_id["features"].kind == MULTI_CHOICE


def test_block_options_are_preserved_per_question():
    req = map_feed_item(_three_question_item())
    by_id = {b.block_id: b for b in req.document.blocks}

    assert [o.id for o in by_id["features"].options] == ["a", "b", "c"]
    assert [o.label for o in by_id["features"].options] == ["Auth", "Billing", "Cache"]
