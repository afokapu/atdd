# URN: test:mediate-worker-decisions:coach-runtime:L006-UNIT-001-pure-next-after-cursor
# Acceptance: acc:mediate-worker-decisions:L006-UNIT-001-pure-next-after-cursor
# WMBT: wmbt:mediate-worker-decisions:L006
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""L006-UNIT-001 — the pure cursor core selects the next record past the offset.

`next_escalation_after` returns the first record after the persisted cursor and
the advanced cursor; at (or past) the end of the ledger it returns no record and
leaves the cursor unchanged. No I/O, no clock.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.coach_runtime.src.domain.cursor import (
    next_escalation_after,
)

_A = {"escalation_id": "e-a", "request_id": "r-a", "cause": "worker_stuck"}
_B = {"escalation_id": "e-b", "request_id": "r-b", "cause": "dangerous_action"}


def test_returns_first_record_past_offset_and_advances():
    record, new_cursor = next_escalation_after([_A, _B], 0)
    assert record == _A
    assert new_cursor == 1


def test_offset_one_returns_second_record():
    record, new_cursor = next_escalation_after([_A, _B], 1)
    assert record == _B
    assert new_cursor == 2


def test_end_of_ledger_returns_none_and_keeps_cursor():
    record, new_cursor = next_escalation_after([_A, _B], 2)
    assert record is None
    assert new_cursor == 2


def test_empty_ledger_returns_none():
    record, new_cursor = next_escalation_after([], 0)
    assert record is None
    assert new_cursor == 0
