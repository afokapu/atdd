# URN: test:mediate-worker-decisions:bridge-cmux-feed:E011-UNIT-003-safety-gate-unchanged-decider-not-consulted
# Acceptance: acc:mediate-worker-decisions:E011-UNIT-003-safety-gate-unchanged-decider-not-consulted
# WMBT: wmbt:mediate-worker-decisions:E011
# Phase: RED
# Layer: application
# Assertion: behavioral
"""E011-UNIT-003 — the safety gate still escalates before the convention-loaded decider.

Loading the coach convention into the decider must not weaken the rule-based
dangerous-action safety gate: a dangerous permission item escalates and the
convention-loaded decider's provider CLI is NEVER invoked (the gate runs first).
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.bridge_cmux_feed.composition import build_feed_runner
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import FeedItem
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.integration.llm_coach import (
    LlmCoach,
)
from atdd.mediate_worker_decisions.bridge_cmux_feed.tests._helpers import (
    FakeFeedSource,
    FakeFeedTransport,
)


def test_dangerous_item_escalates_without_invoking_the_convention_loaded_decider():
    cli_calls = []

    def _recording_cli(prompt, *, system=None, timeout):
        cli_calls.append((prompt, system))
        return "Use the shim"

    # a real convention-loaded decider, but the provider CLI records every call
    coach = LlmCoach(
        cli=_recording_cli,
        coach_context="coach convention text",
        id_factory=lambda: "esc-1",
        ts_factory=lambda: "t",
    )

    item = FeedItem(
        id="f1",
        request_id="req-danger",
        kind="permissionRequest",
        tool_name="Bash",
        tool_input="git push origin main",
    )
    transport = FakeFeedTransport()
    runner = build_feed_runner(
        source=FakeFeedSource([item]),
        reply=transport,
        coach=coach,
    )

    outcome = runner.handle(item)

    assert outcome.escalation is not None
    assert outcome.escalation.cause == "dangerous_action"
    assert transport.calls == []      # no auto reply for a dangerous tool use
    assert cli_calls == []            # the decider was never consulted — gate runs first
