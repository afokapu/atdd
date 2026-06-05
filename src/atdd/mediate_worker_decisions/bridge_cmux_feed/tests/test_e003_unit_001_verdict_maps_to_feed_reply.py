# URN: test:mediate-worker-decisions:bridge-cmux-feed:E003-UNIT-001-verdict-maps-to-feed-reply
# Acceptance: acc:mediate-worker-decisions:E003-UNIT-001-verdict-maps-to-feed-reply
# WMBT: wmbt:mediate-worker-decisions:E003
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""E003-UNIT-001 — a verdict maps to the correct feed reply verb and params.

A question-kind auto_apply verdict yields ``feed.question.reply`` with
request_id + selections; a permission-kind auto_apply verdict yields
``feed.permission.reply`` with request_id + decision.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import (
    PERMISSION,
    QUESTION,
)
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_reply_mapper import (
    plan_reply,
)
from atdd.mediate_worker_decisions.mediate_decision.src.domain.verdict import (
    AUTO_APPLY, SOURCE_COACH, Verdict,
)


def test_question_verdict_yields_question_reply():
    verdict = Verdict(
        verdict_id="v1", request_id="req-q", decided_at="t",
        disposition=AUTO_APPLY, source=SOURCE_COACH,
        selected_option_id="Alpha", reason="ok",
    )

    plan = plan_reply(verdict, kind=QUESTION)

    assert plan.verb == "feed.question.reply"
    assert plan.params["request_id"] == "req-q"
    assert plan.params["selections"] == ["Alpha"]


def test_permission_verdict_yields_permission_reply():
    verdict = Verdict(
        verdict_id="v2", request_id="req-p", decided_at="t",
        disposition=AUTO_APPLY, source=SOURCE_COACH,
        selected_option_id=None, reason="ok",
    )

    plan = plan_reply(verdict, kind=PERMISSION)

    assert plan.verb == "feed.permission.reply"
    assert plan.params["request_id"] == "req-p"
    # cmux requires ``mode`` (not ``decision``) ∈ once|always|all|bypass|deny (#980/#981).
    assert plan.params["mode"] == "once"
