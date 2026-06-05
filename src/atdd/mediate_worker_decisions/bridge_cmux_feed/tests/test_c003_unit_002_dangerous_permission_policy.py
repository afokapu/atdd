# URN: test:mediate-worker-decisions:bridge-cmux-feed:C003-UNIT-002-dangerous-permission-policy-deny-or-escalate
# Acceptance: acc:mediate-worker-decisions:C003-UNIT-002-dangerous-permission-policy-deny-or-escalate
# WMBT: wmbt:mediate-worker-decisions:C003
# Phase: GREEN
# Layer: application
# Assertion: behavioral
"""C003-UNIT-002 — the coach's dangerous-permission policy (#981).

A dangerous permission is NEVER auto-approved and the coach is never consulted.
Under the ``deny`` policy the runner actively denies it via
``feed.permission.reply {mode: deny}`` (so an unattended worker is not stalled at
the 120s soft-wait) and records the escalation; under the default ``escalate``
policy no reply is sent and the item is escalated for a human.
"""
from __future__ import annotations

import pytest

from atdd.mediate_worker_decisions.bridge_cmux_feed.composition import build_feed_runner
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import (
    PERMISSION,
    FeedItem,
)
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_reply_mapper import (
    DANGEROUS_DENY,
    DANGEROUS_ESCALATE,
)

from ._helpers import FakeCoach, FakeFeedSource, FakeFeedTransport

pytestmark = [pytest.mark.coder]

_DANGER = FeedItem(id="i1", request_id="r1", kind=PERMISSION, tool_name="Bash", tool_input="rm -rf /")


def _run(policy):
    transport = FakeFeedTransport()
    coach = FakeCoach()
    runner = build_feed_runner(
        source=FakeFeedSource([_DANGER]),
        reply=transport,
        coach=coach,
        id_factory=lambda: "esc-id",
        ts_factory=lambda: "t",
        dangerous_permission_policy=policy,
    )
    outcomes = runner.run_once()
    return transport, coach, outcomes


def test_deny_policy_actively_denies_and_escalates():
    transport, coach, outcomes = _run(DANGEROUS_DENY)
    assert transport.calls == [("feed.permission.reply", {"request_id": "r1", "mode": "deny"})]
    assert outcomes[0].escalation is not None
    assert coach.calls == []  # dangerous never reaches the coach


def test_escalate_policy_sends_no_reply():
    transport, coach, outcomes = _run(DANGEROUS_ESCALATE)
    assert transport.calls == []  # no auto reply — human decides via the Feed
    assert outcomes[0].escalation is not None
    assert coach.calls == []


def test_dangerous_is_never_auto_approved_under_either_policy():
    for policy in (DANGEROUS_DENY, DANGEROUS_ESCALATE):
        transport, _, _ = _run(policy)
        approve = [c for c in transport.calls if c[1].get("mode") == "once"]
        assert approve == [], f"dangerous action must never be allowed (policy={policy})"
