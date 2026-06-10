# URN: test:mediate-worker-decisions:coach-answer-escalation:E014-UNIT-001-permission-reply-verb-and-params
# Acceptance: acc:mediate-worker-decisions:E014-UNIT-001-permission-reply-verb-and-params
# WMBT: wmbt:mediate-worker-decisions:E014
# Phase: RED
# Layer: application
# Assertion: behavioral
"""E014-UNIT-001 — ``atdd coach answer`` on a permission item builds the right reply.

The ``once`` verb yields ``feed.permission.reply`` with the request_id and
``mode: once``; the ``deny`` verb yields the same verb with ``mode: deny``. The
assertion is on the cmux RPC verb and params, not a log line.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import (
    PERMISSION,
    FeedItem,
)
from atdd.mediate_worker_decisions.coach_answer_escalation.src.application.answer_escalation import (
    plan_answer,
)


def _permission_item() -> FeedItem:
    return FeedItem(
        id="i-1",
        request_id="req-p",
        kind=PERMISSION,
        tool_name="Bash",
        tool_input="git push origin main",
    )


def test_once_verb_yields_permission_reply_once():
    plan = plan_answer(_permission_item(), "once")

    assert plan.verb == "feed.permission.reply"
    assert plan.params["request_id"] == "req-p"
    assert plan.params["mode"] == "once"


def test_deny_verb_yields_permission_reply_deny():
    plan = plan_answer(_permission_item(), "deny")

    assert plan.verb == "feed.permission.reply"
    assert plan.params["request_id"] == "req-p"
    assert plan.params["mode"] == "deny"
