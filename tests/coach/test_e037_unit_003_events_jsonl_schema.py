# URN: test:govern-lifecycle:define-validator-report-and-persistence-materialization-contract:E037-UNIT-003-events-jsonl-schema
# Acceptance: acc:govern-lifecycle:E037-UNIT-003-events-jsonl-schema
"""Unit test for E037-UNIT-003 (docs/coach-decomposition.md §5.2).

``atdd.train.events`` freezes the events.jsonl schema at ``schema_version 1.0``,
enumerates the §5.2 initial event types with their required payload keys, and
validates event dicts purely (no I/O).
"""
from __future__ import annotations

import pytest

from atdd.train.events import (
    EVENT_TYPES,
    REQUIRED_EVENT_FIELDS,
    SCHEMA_VERSION,
    validate_event_dict,
)

pytestmark = pytest.mark.atdd_validator

# The initial event-type set from docs/coach-decomposition.md §5.2.
_INITIAL_EVENT_TYPES = {
    "RunStarted",
    "EvidenceMaterialized",
    "DecisionMade",
    "DispatchEmitted",
    "AgentSpawned",
    "AgentReady",
    "AgentEventReceived",
    "AgentDone",
    "PhaseAdvanced",
    "PrOpened",
    "PrMerged",
    "RunBlocked",
    "RunEscalated",
    "RunCompleted",
    "RunResumed",
}


def test_schema_version_is_1_0_with_required_top_level_fields():
    assert SCHEMA_VERSION == "1.0"
    assert {
        "schema_version",
        "ts",
        "run_id",
        "issue_number",
        "type",
        "payload",
        "seq",
    } <= set(REQUIRED_EVENT_FIELDS)


def test_event_types_cover_the_5_2_initial_set():
    missing = _INITIAL_EVENT_TYPES - set(EVENT_TYPES)
    assert not missing, f"events schema missing §5.2 types: {sorted(missing)}"


def test_validate_event_dict_accepts_valid_and_flags_invalid():
    valid = {
        "schema_version": "1.0",
        "ts": "2026-05-31T00:00:00Z",
        "run_id": "run-890",
        "issue_number": 890,
        "type": "DecisionMade",
        "seq": 1,
        "payload": {
            "verdict_kind": "proceed",
            "from_phase": "RED",
            "to_phase": "GREEN",
            "persona": "coder",
            "rule_ids": [],
        },
    }
    assert validate_event_dict(valid) == ()
    assert validate_event_dict({}) != ()  # missing every required field
    assert validate_event_dict(dict(valid, type="NotARealType")) != ()
    assert validate_event_dict(dict(valid, schema_version="2.0")) != ()  # major mismatch
    no_payload_key = dict(valid)
    no_payload_key["payload"] = {}  # DecisionMade requires payload keys
    assert validate_event_dict(no_payload_key) != ()
