# URN: test:mediate-worker-decisions:sense-decision:C001-UNIT-001-no-false-positive
# Acceptance: acc:mediate-worker-decisions:C001-UNIT-001-no-false-positive
# WMBT: wmbt:mediate-worker-decisions:C001
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""C001-UNIT-001 — non-decision output yields no request."""
from __future__ import annotations

import pytest

from atdd.mediate_worker_decisions.sense_decision.src.domain.prompt_parser import parse_prompt


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   \n  \n",
        "Building... [####------] 40%\n",
        "Proceed with the migration?\n",          # question, no options (half-rendered)
        "Only one option here:\n1) lonely\n",     # single bullet is a list, not a decision
    ],
)
def test_c001_unit_001_no_false_positive(text):
    assert parse_prompt(text) is None
