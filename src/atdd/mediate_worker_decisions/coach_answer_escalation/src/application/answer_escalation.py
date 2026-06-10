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

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.application.ports import (
    FeedReply,
    FeedSource,
)
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import (
    PERMISSION,
    QUESTION,
    FeedItem,
    FeedReplyPlan,
)
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_reply_mapper import (
    PERMISSION_ALLOW,
    PERMISSION_DENY,
)
from atdd.mediate_worker_decisions.coach_answer_escalation.src.domain.label_resolver import (
    resolve_exact_label,
)

# the operator verbs accepted for a permission item, mapped to the cmux mode.
_PERMISSION_MODES = {"once": PERMISSION_ALLOW, "deny": PERMISSION_DENY}


def plan_answer(item: FeedItem, verb: str) -> FeedReplyPlan:
    """Build the cmux feed reply plan for ``item`` given the operator's ``verb``.

    For a permission item, ``verb`` is ``once`` or ``deny``. For a question item,
    ``verb`` is the operator's chosen option, resolved to the exact option label.
    """
    if item.kind == PERMISSION:
        try:
            mode = _PERMISSION_MODES[verb]
        except KeyError:
            raise ValueError(
                f"{verb!r} is not a permission verb; expected one of {sorted(_PERMISSION_MODES)}"
            ) from None
        return FeedReplyPlan(
            verb="feed.permission.reply",
            params={"request_id": item.request_id, "mode": mode},
        )
    if item.kind == QUESTION:
        labels = [opt["label"] for opt in item.question_options]
        # resolve_exact_label raises loudly on a mismatch BEFORE any reply (C009)
        label = resolve_exact_label(verb, labels)
        return FeedReplyPlan(
            verb="feed.question.reply",
            params={"request_id": item.request_id, "selections": [label]},
        )
    raise ValueError(f"unanswerable feed item kind: {item.kind!r}")


class AnswerEscalationUseCase:
    """Resolve a request_id to its pending item, plan the answer, deliver once."""

    def __init__(self, *, source: FeedSource, reply: FeedReply) -> None:
        self._source = source
        self._reply = reply

    def answer(self, request_id: str, verb: str) -> FeedReplyPlan:
        """Look up the pending item for ``request_id`` and deliver the reply."""
        item = self._find_pending(request_id)
        plan = plan_answer(item, verb)  # raises loudly before deliver on a mismatch
        self._reply.deliver(plan)
        return plan

    def _find_pending(self, request_id: str) -> FeedItem:
        for item in self._source.list_pending():
            if item.request_id == request_id:
                return item
        raise KeyError(f"no pending feed item for request_id {request_id!r}")
