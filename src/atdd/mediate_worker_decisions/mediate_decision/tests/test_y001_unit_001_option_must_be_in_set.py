# URN: test:mediate-worker-decisions:mediate-decision:Y001-UNIT-001-option-must-be-in-set
# Acceptance: acc:mediate-worker-decisions:Y001-UNIT-001-option-must-be-in-set
# WMBT: wmbt:mediate-worker-decisions:Y001
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""Y001-UNIT-001 — selected option must be one offered to the worker."""
from __future__ import annotations

from atdd.mediate_worker_decisions.mediate_decision.src.domain.coach_reply_parser import (
    selection_in_options,
)


def test_in_set_accepted():
    assert selection_in_options("1", ["1", "2"]) is True


def test_out_of_set_rejected():
    assert selection_in_options("9", ["1", "2"]) is False
