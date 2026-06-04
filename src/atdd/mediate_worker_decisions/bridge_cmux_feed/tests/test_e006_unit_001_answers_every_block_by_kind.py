# URN: test:mediate-worker-decisions:bridge-cmux-feed:E006-UNIT-001-answers-every-block-by-kind
# Acceptance: acc:mediate-worker-decisions:E006-UNIT-001-answers-every-block-by-kind
# WMBT: wmbt:mediate-worker-decisions:E006
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""E006-UNIT-001 — the decider answers EVERY block, each of the correct kind.

Given a four-block document (single_choice, single_choice, multi_choice,
free_text) the decider (LlmCoach over a fake provider cli) must return one
structured answer per block: a single option for single_choice, a LIST for
multi_choice, and text for free_text — never just the first.
"""
from __future__ import annotations

import json

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.integration.llm_coach import (
    LlmCoach,
)
from atdd.mediate_worker_decisions.sense_decision.src.domain.decision_document import (
    FREE_TEXT,
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


def _doc_request() -> DecisionRequest:
    document = DecisionDocument(
        blocks=(
            Block("color", SINGLE_CHOICE, "Pick a color",
                  options=(Option("blue", "Blue"), Option("red", "Red"))),
            Block("size", SINGLE_CHOICE, "Pick a size",
                  options=(Option("s", "Small"), Option("m", "Medium"))),
            Block("features", MULTI_CHOICE, "Pick the features",
                  options=(Option("a", "Auth"), Option("b", "Billing"), Option("c", "Cache"))),
            Block("notes", FREE_TEXT, "Any notes?"),
        )
    )
    return DecisionRequest(
        request_id="req-multi",
        worker=WorkerRef(surface_id="s1", agent_handle_ref="req-multi"),
        prompt=DecisionPrompt(raw_text="", question="Pick a color", options=()),
        source="cmux_feed",
        created_at="",
        document=document,
    )


def _fake_cli(prompt, *, timeout):
    # The decider renders the whole document and parses a per-block answer.
    return json.dumps(
        {
            "answers": [
                {"block_id": "color", "selected_ids": ["blue"]},
                {"block_id": "size", "selected_ids": ["m"]},
                {"block_id": "features", "selected_ids": ["a", "c"]},
                {"block_id": "notes", "text": "prefer tabs"},
            ]
        }
    )


def test_decider_returns_one_answer_per_block_of_correct_kind():
    coach = LlmCoach(
        cli=_fake_cli,
        id_factory=lambda: "v1",
        ts_factory=lambda: "t",
    )

    verdict = coach.mediate(_doc_request())

    answer = verdict.answer
    assert answer is not None, "the decider must answer the whole document"
    assert {a.block_id for a in answer.answers} == {"color", "size", "features", "notes"}

    features = answer.for_block("features")
    assert [o.id for o in features.selected] == ["a", "c"]  # a LIST, not flattened

    assert [o.id for o in answer.for_block("color").selected] == ["blue"]
    assert answer.for_block("notes").text == "prefer tabs"
