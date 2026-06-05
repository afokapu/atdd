# URN: test:mediate-worker-decisions:bridge-cmux-feed:L002-UNIT-001-maps-feed-item-to-request
# Acceptance: acc:mediate-worker-decisions:L002-UNIT-001-maps-feed-item-to-request
# WMBT: wmbt:mediate-worker-decisions:L002
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""L002-UNIT-001 — a pending feed item maps to a DecisionRequest.

A question item yields a request whose options carry the option ids/labels and
whose worker carries the feed request_id; a permission item yields a request
whose prompt exposes the tool_input for the safety gate.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import FeedItem
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item_mapper import (
    map_feed_item,
)


def test_question_item_maps_options_and_request_id():
    item = FeedItem(
        id="f1",
        request_id="req-q",
        kind="question",
        question_prompt="Which approach?",
        question_options=(
            {"id": "o0", "label": "Alpha", "description": "first"},
            {"id": "o1", "label": "Beta", "description": "second"},
        ),
        tool_name=None,
        tool_input=None,
    )

    req = map_feed_item(item)

    assert req.request_id == "req-q"
    # the worker ref carries the feed request_id so the reply routes back
    assert req.worker.agent_handle_ref == "req-q"
    assert [o.id for o in req.prompt.options] == ["o0", "o1"]
    assert [o.label for o in req.prompt.options] == ["Alpha", "Beta"]


def test_permission_item_exposes_tool_input_for_safety_gate():
    item = FeedItem(
        id="f2",
        request_id="req-p",
        kind="permissionRequest",
        question_prompt=None,
        question_options=(),
        tool_name="Bash",
        tool_input="ls -la",
    )

    req = map_feed_item(item)

    assert req.request_id == "req-p"
    # the tool_input must be visible to the danger gate downstream
    assert "ls -la" in req.prompt.raw_text
