# URN: test:mediate-worker-decisions:mediate-decision:E001-UNIT-001-parse-or-error
# Acceptance: acc:mediate-worker-decisions:E001-UNIT-001-parse-or-error
# WMBT: wmbt:mediate-worker-decisions:E001
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""E001-UNIT-001 — well-formed reply parses; malformed raises (no guessing)."""
from __future__ import annotations

import pytest

from atdd.mediate_worker_decisions.mediate_decision.src.domain.coach_reply_parser import (
    CoachReplyParseError,
    parse_reply,
)


def test_parses_decision_and_reason():
    decision, reason = parse_reply("DECISION: 1\nREASON: looks safe")
    assert decision == "1"
    assert reason == "looks safe"


def test_malformed_raises():
    with pytest.raises(CoachReplyParseError):
        parse_reply("I think option one is fine")
