# URN: test:mediate-worker-decisions:bridge-cmux-feed:E006-UNIT-002-selection-constrained-to-block-options
# Acceptance: acc:mediate-worker-decisions:E006-UNIT-002-selection-constrained-to-block-options
# WMBT: wmbt:mediate-worker-decisions:E006
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""E006-UNIT-002 — each block's answer is drawn only from that block's options.

A single_choice answer is one of its own options; a multi_choice answer is a
subset of its own options. An id the coach names that is NOT in the block is
never carried through (no cross-block bleed, no hallucinated option).
"""
from __future__ import annotations

import json

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.integration.llm_coach import (
    LlmCoach,
)
from atdd.mediate_worker_decisions.sense_decision.src.domain.decision_document import (
    MULTI_CHOICE,
    SINGLE_CHOICE,
    Block,
    DecisionDocument,
)
from atdd.mediate_worker_decisions.sense_decision.src.domain.decision_request import (
    DecisionPrompt,
    DecisionRequest,
    Option,
    WorkerRef,
)


def _request() -> DecisionRequest:
    document = DecisionDocument(
        blocks=(
            Block("color", SINGLE_CHOICE, "Pick a color",
                  options=(Option("blue", "Blue"), Option("red", "Red"))),
            Block("features", MULTI_CHOICE, "Pick the features",
                  options=(Option("a", "Auth"), Option("b", "Billing"), Option("c", "Cache"))),
        )
    )
    return DecisionRequest(
        request_id="req-x",
        worker=WorkerRef(surface_id="s1"),
        prompt=DecisionPrompt(raw_text="", question="Pick a color", options=()),
        source="cmux_feed",
        created_at="",
        document=document,
    )


def _fake_cli(prompt, *, timeout):
    # "purple" is NOT a color option and "z" is NOT a feature option — both must
    # be dropped; only in-block ids survive.
    return json.dumps(
        {
            "answers": [
                {"block_id": "color", "selected_ids": ["blue", "purple"]},
                {"block_id": "features", "selected_ids": ["a", "z", "c"]},
            ]
        }
    )


def test_each_block_answer_is_constrained_to_its_options():
    coach = LlmCoach(cli=_fake_cli, id_factory=lambda: "v", ts_factory=lambda: "t")

    answer = coach.mediate(_request()).answer
    assert answer is not None

    color_ids = {o.id for o in answer.for_block("color").selected}
    feature_ids = {o.id for o in answer.for_block("features").selected}

    assert color_ids <= {"blue", "red"}
    assert "purple" not in color_ids
    assert feature_ids <= {"a", "b", "c"}
    assert "z" not in feature_ids
