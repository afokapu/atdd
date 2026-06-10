"""``atdd coach answer`` — plan + deliver the operator's reply (WMBT E014).

The operator's direct reply command for a parked worker (Track A, no engine).
``plan_answer`` maps a pending feed item + the operator's verb to a
``FeedReplyPlan`` through the existing reply grammar:

  * permission item → ``feed.permission.reply {request_id, mode: once|deny}``
  * question item   → ``feed.question.reply {request_id, selections:[label]}``
    with the operator's choice resolved to the EXACT ``question_options[].label``
    (a mismatch raises loudly — see ``label_resolver``).

``AnswerEscalationUseCase`` looks the item up by request_id via a ``FeedSource``
and delivers the plan via a ``FeedReply`` (deduped — exactly once per request_id).

Skeleton: bodies land in GREEN.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import (
    FeedItem,
    FeedReplyPlan,
)


def plan_answer(item: FeedItem, verb: str) -> FeedReplyPlan:
    """Build the cmux feed reply plan for ``item`` given the operator's ``verb``.

    For a permission item, ``verb`` is ``once`` or ``deny``. For a question item,
    ``verb`` is the operator's chosen option, resolved to the exact option label.
    """
    raise NotImplementedError("wmbt:mediate-worker-decisions:E014")


class AnswerEscalationUseCase:
    """Resolve a request_id to its pending item, plan the answer, deliver once."""

    def __init__(self, *, source, reply) -> None:
        self._source = source
        self._reply = reply

    def answer(self, request_id: str, verb: str) -> FeedReplyPlan:
        """Look up the pending item for ``request_id`` and deliver the reply."""
        raise NotImplementedError("wmbt:mediate-worker-decisions:E014")
