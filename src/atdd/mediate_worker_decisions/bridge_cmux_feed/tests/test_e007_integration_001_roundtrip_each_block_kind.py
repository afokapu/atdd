# URN: test:mediate-worker-decisions:bridge-cmux-feed:E007-INTEGRATION-001-roundtrip-each-block-kind
# Acceptance: acc:mediate-worker-decisions:E007-INTEGRATION-001-roundtrip-each-block-kind
# WMBT: wmbt:mediate-worker-decisions:E007
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""E007-INTEGRATION-001 — block kinds survive mapper -> decider -> reply.

A multi-block question item (single + multi/checkbox, plus a free_text block the
decider answers but cmux can't carry) and a safe permission item are driven
end-to-end through the real runner. The recorded feed.question.reply carries a
flat selections list covering every CHOICE question (the checkbox contributing
multiple labels); the free_text block is answered by the decider but not carried
in the cmux question reply; the safe permission round-trips as a decision.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.bridge_cmux_feed.composition import build_feed_runner
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import FeedItem
from atdd.mediate_worker_decisions.bridge_cmux_feed.tests._helpers import (
    FakeFeedSource,
    FakeFeedTransport,
)
from atdd.mediate_worker_decisions.sense_decision.src.domain.decision_document import (
    FREE_TEXT,
    MULTI_CHOICE,
    DecisionAnswer,
    BlockAnswer,
)
from atdd.mediate_worker_decisions.mediate_decision.src.domain.verdict import (
    AUTO_APPLY,
    SOURCE_COACH,
    Verdict,
)

MULTI_QUESTION = FeedItem(
    id="f-q",
    request_id="req-q",
    kind="question",
    question_prompt="Pick a color",
    question_options=({"id": "blue", "label": "Blue", "description": ""},),
    questions=(
        {"id": "color", "header": "Color", "prompt": "Pick a color", "multi_select": False,
         "options": [{"id": "blue", "label": "Blue"}, {"id": "red", "label": "Red"}]},
        {"id": "features", "header": "Features", "prompt": "Pick features", "multi_select": True,
         "options": [{"id": "a", "label": "Auth"}, {"id": "b", "label": "Billing"}]},
        {"id": "notes", "header": "Notes", "prompt": "Any notes?", "kind": "free_text",
         "options": []},
    ),
)

SAFE_PERMISSION = FeedItem(
    id="f-p",
    request_id="req-p",
    kind="permissionRequest",
    tool_name="Bash",
    tool_input="ls -la",
)


class DocAnsweringCoach:
    """A fake decider that answers the whole document (first option per choice,
    all options for multi, fixed text for free_text); permission items get a
    plain auto verdict (no document)."""

    def mediate(self, request):
        answer = None
        document = getattr(request, "document", None)
        if document is not None:
            block_answers = []
            for block in document.blocks:
                if block.kind == MULTI_CHOICE:
                    block_answers.append(
                        BlockAnswer(block.block_id, block.kind, selected=tuple(block.options))
                    )
                elif block.kind == FREE_TEXT:
                    block_answers.append(
                        BlockAnswer(block.block_id, block.kind, text="looks good")
                    )
                else:
                    block_answers.append(
                        BlockAnswer(block.block_id, block.kind, selected=(block.options[0],))
                    )
            answer = DecisionAnswer(answers=tuple(block_answers))
        return Verdict(
            verdict_id="v",
            request_id=request.request_id,
            decided_at="t",
            disposition=AUTO_APPLY,
            source=SOURCE_COACH,
            selected_option_id=None,
            reason="auto",
            answer=answer,
        )


def test_each_block_kind_round_trips_to_its_reply_shape():
    transport = FakeFeedTransport()
    runner = build_feed_runner(
        source=FakeFeedSource([MULTI_QUESTION, SAFE_PERMISSION]),
        reply=transport,
        coach=DocAnsweringCoach(),
    )

    runner.run_once()

    q = next(p for v, p in transport.calls if v == "feed.question.reply")
    # one flat selections list covering every CHOICE question: color (single)
    # + features (checkbox, BOTH labels). The free_text "notes" block is answered
    # by the decider but contributes no label to the cmux question reply.
    assert q["selections"] == ["Blue", "Auth", "Billing"]

    p = next(pr for v, pr in transport.calls if v == "feed.permission.reply")
    assert p["decision"] == "once"  # confirm/permission round-trips
