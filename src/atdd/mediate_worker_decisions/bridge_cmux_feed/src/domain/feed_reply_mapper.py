"""Pure mapper: a coach Verdict -> a FeedReplyPlan (WMBT E003/E007).

Each feed item kind has its own ``feed.*.reply`` verb. ``feed.question.reply``
takes a single FLAT ``selections: [string]`` list of chosen option labels — cmux
routes each label to its question by option membership (verified live against
cmux). So a multi-question answer is delivered as the concatenation of EVERY
block's chosen labels (a single_choice contributes its one label, a
multi_choice/checkbox contributes all of its chosen labels) — covering every
question, not only the first (the live bug was a list carrying just the first
question's selection). A single-question verdict carries its one label for
back-compat. A permission reply carries a ``decision`` (auto_apply -> ``once``);
an exitPlan reply just acknowledges.

free_text / confirm blocks are answered by the decider (WMBT E006) but are not
carried in a cmux ``feed.question.reply`` (cmux AskUserQuestion sub-questions are
choice-based); they contribute no label to ``selections``.
"""
from __future__ import annotations

from typing import List

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
        return _question_reply(verdict)
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


def _question_reply(verdict: Verdict) -> FeedReplyPlan:
    answer = verdict.answer
    if answer is not None and answer.answers:
        # flat selections covering EVERY question — every block's chosen labels,
        # in document order (cmux routes each label to its question).
        selections: List[str] = []
        for block_answer in answer.answers:
            selections.extend(opt.label for opt in block_answer.selected)
        if not selections and verdict.selected_option_id:
            selections = [verdict.selected_option_id]
        return FeedReplyPlan(
            verb="feed.question.reply",
            params={"request_id": verdict.request_id, "selections": selections},
        )

    # legacy single-question verdict
    return FeedReplyPlan(
        verb="feed.question.reply",
        params={
            "request_id": verdict.request_id,
            "selections": [verdict.selected_option_id],
        },
    )
