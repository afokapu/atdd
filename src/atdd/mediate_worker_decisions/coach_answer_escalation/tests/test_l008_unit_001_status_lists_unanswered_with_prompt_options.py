# URN: test:mediate-worker-decisions:coach-answer-escalation:L008-UNIT-001-status-lists-unanswered-with-prompt-options
# Acceptance: acc:mediate-worker-decisions:L008-UNIT-001-status-lists-unanswered-with-prompt-options
# WMBT: wmbt:mediate-worker-decisions:L008
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""L008-UNIT-001 — status lists each unanswered escalation with its prompt/options.

Two escalation records whose request_ids are both still pending in the Feed are
listed, each enriched with the prompt and option labels the operator needs to
choose a label for ``atdd coach answer``.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import (
    QUESTION,
    FeedItem,
)
from atdd.mediate_worker_decisions.coach_answer_escalation.src.domain.escalation_surfacing import (
    list_unanswered_escalations,
)


def _pending(request_id: str, prompt: str, labels):
    return FeedItem(
        id="i-" + request_id,
        request_id=request_id,
        kind=QUESTION,
        question_prompt=prompt,
        question_options=tuple({"id": f"o{i}", "label": l} for i, l in enumerate(labels)),
    )


def test_lists_both_unanswered_with_prompt_and_options():
    escalations = [
        {"escalation_id": "e1", "request_id": "req-a", "cause": "operator_reserved"},
        {"escalation_id": "e2", "request_id": "req-b", "cause": "operator_reserved"},
    ]
    pending = [
        _pending("req-a", "Approve phase → RED?", ["Approve", "Reject"]),
        _pending("req-b", "Pick a backend", ["Postgres", "SQLite"]),
    ]

    result = list_unanswered_escalations(escalations, pending)

    by_req = {u.request_id: u for u in result}
    assert set(by_req) == {"req-a", "req-b"}
    assert by_req["req-a"].prompt == "Approve phase → RED?"
    assert by_req["req-a"].options == ("Approve", "Reject")
    assert by_req["req-b"].options == ("Postgres", "SQLite")
