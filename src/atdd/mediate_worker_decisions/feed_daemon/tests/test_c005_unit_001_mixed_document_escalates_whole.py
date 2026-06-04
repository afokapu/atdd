# URN: test:mediate-worker-decisions:feed-daemon:C005-UNIT-001-mixed-document-escalates-whole
# Acceptance: acc:mediate-worker-decisions:C005-UNIT-001-mixed-document-escalates-whole
# WMBT: wmbt:mediate-worker-decisions:C005
# Phase: RED
# Layer: backend
# Assertion: behavioral
"""C005-UNIT-001 — a mixed document with a dangerous block escalates whole.

The headline (non-negotiable) safety property: when a decision document mixes a
safe choice block with a dangerous confirm block, the daemon escalates the WHOLE
document (document-atomic) and delivers NO feed reply — a cmux item is answered
atomically, so a single item is never partially replied. A dangerous block is
never auto-answered.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import FeedItem
from atdd.mediate_worker_decisions.feed_daemon.tests._helpers import (
    RecordingEscalationSink,
    make_daemon,
)

MIXED_DOCUMENT = FeedItem(
    id="f-mix",
    request_id="req-mix",
    kind="question",
    question_prompt="Pick a color",
    question_options=({"id": "blue", "label": "Blue", "description": ""},),
    questions=(
        {"id": "color", "header": "Color", "prompt": "Pick a color", "multi_select": False,
         "options": [{"id": "blue", "label": "Blue"}, {"id": "red", "label": "Red"}]},
        # a dangerous confirm block composed into the same document
        {"id": "deploy", "header": "Deploy", "kind": "confirm",
         "prompt": "Approve running: git push origin main",
         "options": [{"id": "approve", "label": "Approve"}, {"id": "deny", "label": "Deny"}]},
    ),
)


def test_mixed_document_escalates_and_is_never_auto_answered():
    sink = RecordingEscalationSink()
    daemon, source, transport, coach = make_daemon(
        items=[MIXED_DOCUMENT],
        escalation_sink=sink,
    )

    daemon.tick()

    # the whole document is escalated ...
    assert len(sink.records) == 1
    assert sink.records[0].request_id == "req-mix"
    # ... and NO reply is delivered for it (document-atomic, never partial)
    assert all(v != "feed.question.reply" for v, _ in transport.calls)
