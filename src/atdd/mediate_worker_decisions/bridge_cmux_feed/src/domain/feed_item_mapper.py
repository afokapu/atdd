"""Pure mapper: a cmux Feed item -> a contract-shaped DecisionRequest (WMBT L002/L003).

Branches on ``FeedItem.kind``. A question is mapped to the FULL decision
document: every entry of ``questions[]`` becomes a block (single_choice, or
multi_choice when ``multi_select``), preserving order/ids/options — never
flattened to the first question (WMBT L003). The flat ``prompt`` is kept as a
single-block back-compat mirror of the first block. A legacy single-question
item (only the ``question_prompt``/``question_options`` mirror, no ``questions``)
still maps to a one-block document.

A permission/exitPlan exposes the ``tool_input`` in the prompt's ``raw_text`` so
the downstream safety gate (WMBT C003) can classify it; those kinds stay on the
item-level path and carry no document. The feed ``request_id`` is carried on the
worker ref so the eventual reply routes back to the right blocked agent.
"""
from __future__ import annotations

from typing import Mapping

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import (
    EXIT_PLAN,
    PERMISSION,
    QUESTION,
    FeedItem,
)
from atdd.mediate_worker_decisions.sense_decision.src.domain.decision_document import (
    CONFIRM,
    FREE_TEXT,
    GROUP,
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

SOURCE_CMUX_FEED = "cmux_feed"

_KNOWN_KINDS = (SINGLE_CHOICE, MULTI_CHOICE, FREE_TEXT, CONFIRM, GROUP)
# cmux/agent aliases for the grammar kinds
_KIND_ALIASES = {"checkbox": MULTI_CHOICE, "permission": CONFIRM}


def map_feed_item(item: FeedItem) -> DecisionRequest:
    document = None
    if item.kind == QUESTION:
        document = _build_document(item)
        first = document.blocks[0]
        question = first.prompt
        options = first.options  # single-block back-compat mirror
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
        document=document,
    )


def _build_document(item: FeedItem) -> DecisionDocument:
    """Build the full block document, preserving every question (WMBT L003)."""
    if item.questions:
        blocks = tuple(_question_to_block(q) for q in item.questions)
    else:
        # legacy single-question item: one block from the top-level mirror
        options = tuple(
            Option(id=str(o["id"]), label=str(o["label"]))
            for o in item.question_options
        )
        blocks = (
            Block(
                block_id="q0",
                kind=SINGLE_CHOICE,
                prompt=item.question_prompt or "",
                options=options,
            ),
        )
    return DecisionDocument(blocks=blocks)


def _question_to_block(question: Mapping) -> Block:
    options = tuple(
        Option(id=str(o.get("id", "")), label=str(o.get("label", "")))
        for o in (question.get("options") or [])
    )
    return Block(
        block_id=str(question.get("id", "")),
        kind=_question_kind(question),
        prompt=str(question.get("prompt", "")),
        header=question.get("header"),
        options=options,
    )


def _question_kind(question: Mapping) -> str:
    """Map a cmux question to a block kind.

    An explicit ``kind`` (honoring the checkbox/permission aliases) wins; else a
    ``multi_select`` question is a multi_choice and everything else a
    single_choice.
    """
    explicit = question.get("kind")
    if explicit in _KNOWN_KINDS:
        return explicit
    if explicit in _KIND_ALIASES:
        return _KIND_ALIASES[explicit]
    return MULTI_CHOICE if question.get("multi_select") else SINGLE_CHOICE
