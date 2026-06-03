"""Pure mapper: a cmux Feed item -> a contract-shaped DecisionRequest (WMBT L002).

Branches on ``FeedItem.kind``. A question carries its options through to the
request; a permission/exitPlan exposes the ``tool_input`` in the prompt's
``raw_text`` so the downstream safety gate (WMBT C003) can classify it. The feed
``request_id`` is carried on the worker ref so the eventual reply routes back to
the right blocked agent.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import (
    EXIT_PLAN,
    PERMISSION,
    QUESTION,
    FeedItem,
)
from atdd.mediate_worker_decisions.sense_decision.src.domain.decision_request import (
    DecisionPrompt,
    DecisionRequest,
    Option,
    WorkerRef,
)

SOURCE_CMUX_FEED = "cmux_feed"


def map_feed_item(item: FeedItem) -> DecisionRequest:
    if item.kind == QUESTION:
        question = item.question_prompt or ""
        options = tuple(
            Option(id=str(o["id"]), label=str(o["label"])) for o in item.question_options
        )
        raw_text = question
    elif item.kind in (PERMISSION, EXIT_PLAN):
        # the tool_input must reach the safety gate verbatim
        raw_text = item.tool_input or ""
        question = item.question_prompt or (
            f"Allow {item.tool_name}?" if item.tool_name else "Allow tool use?"
        )
        options = ()
    else:  # pragma: no cover - guarded for unknown future kinds
        raise ValueError(f"unknown feed item kind: {item.kind!r}")

    return DecisionRequest(
        request_id=item.request_id,
        worker=WorkerRef(surface_id=item.id, agent_handle_ref=item.request_id),
        prompt=DecisionPrompt(raw_text=raw_text, question=question, options=options),
        source=SOURCE_CMUX_FEED,
        created_at="",
    )
