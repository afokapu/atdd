"""Pure mapper: a coach Verdict -> a FeedReplyPlan (WMBT E003).

Each feed item kind has its own ``feed.*.reply`` verb. A question reply carries
``selections`` (the chosen option label); a permission reply carries a
``decision`` (auto_apply maps to ``once``); an exitPlan reply just acknowledges.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import (
    EXIT_PLAN,
    PERMISSION,
    QUESTION,
    FeedReplyPlan,
)
from atdd.mediate_worker_decisions.mediate_decision.src.domain.verdict import Verdict

PERMISSION_ALLOW = "once"


def plan_reply(verdict: Verdict, kind: str) -> FeedReplyPlan:
    if kind == QUESTION:
        return FeedReplyPlan(
            verb="feed.question.reply",
            params={
                "request_id": verdict.request_id,
                "selections": [verdict.selected_option_id],
            },
        )
    if kind == PERMISSION:
        return FeedReplyPlan(
            verb="feed.permission.reply",
            params={"request_id": verdict.request_id, "decision": PERMISSION_ALLOW},
        )
    if kind == EXIT_PLAN:
        return FeedReplyPlan(
            verb="feed.exit_plan.reply",
            params={"request_id": verdict.request_id},
        )
    raise ValueError(f"unknown feed item kind: {kind!r}")
