# URN: test:mediate-worker-decisions:sense-decision:L001-UNIT-001-extracts-latest-prompt
# Acceptance: acc:mediate-worker-decisions:L001-UNIT-001-extracts-latest-prompt
# WMBT: wmbt:mediate-worker-decisions:L001
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""L001-UNIT-001 — parser extracts the latest prompt's question and options."""
from __future__ import annotations

from atdd.mediate_worker_decisions.sense_decision.src.domain.prompt_parser import parse_prompt


def test_l001_unit_001_extracts_latest_prompt():
    text = (
        "Do you want the old thing?\n"
        "1) old-a\n"
        "2) old-b\n"
        "...work happens...\n"
        "Proceed with the migration?\n"
        "1) Apply\n"
        "2) Abort\n"
    )
    prompt = parse_prompt(text)
    assert prompt is not None
    # latest prompt wins
    assert prompt.question == "Proceed with the migration?"
    assert [(o.id, o.label) for o in prompt.options] == [("1", "Apply"), ("2", "Abort")]
