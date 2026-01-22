#!/usr/bin/env python3
"""
Test migration criteria decision algorithm.

SPEC-TESTER-CONV-0034 through SPEC-TESTER-CONV-0043

Validates the contract_needs_migration() function correctly applies
all decision rules in the proper order.
"""

import json
import pytest
from pathlib import Path
from tempfile import NamedTemporaryFile

# pytest pythonpath = . handles imports from repo root

from atdd.coach.commands.migration import contract_needs_migration


def create_test_contract(properties: dict, metadata: dict = None, description: str = "", aspect: str = "test") -> Path:
    """Create a temporary contract file for testing."""
    contract = {
        "$id": f"urn:contract:test:domain:{aspect}",
        "properties": properties,
        "description": description
    }

    if metadata:
        contract["x-artifact-metadata"] = metadata

    # Create temp file with proper naming: {aspect}.schema.json
    temp = NamedTemporaryFile(mode='w', suffix=f'{aspect}.schema.json', delete=False)
    json.dump(contract, temp, indent=2)
    temp.close()

    return Path(temp.name)


# SPEC-TESTER-CONV-0034
def test_entity_with_id_requires_migration():
    """Entity with id field requires migration."""
    contract_path = create_test_contract(
        properties={
            "id": {"type": "string", "pattern": "^[0-9a-f]{8}"},
            "player_id": {"type": "string"},
            "status": {"type": "string"}
        },
        aspect="session"
    )

    try:
        assert contract_needs_migration(contract_path) == True
    finally:
        contract_path.unlink()


# SPEC-TESTER-CONV-0035
def test_event_signals_no_migration():
    """Event signals (past tense, no id) do not require migration."""
    # Test multiple event patterns
    event_aspects = ["exhausted", "succeeded", "failed", "registered", "terminated"]

    for aspect in event_aspects:
        contract_path = create_test_contract(
            properties={
                "timestamp": {"type": "string", "format": "date-time"},
                "player_id": {"type": "string"}
            },
            aspect=aspect
        )

        try:
            assert contract_needs_migration(contract_path) == False, f"{aspect} should not require migration"
        finally:
            contract_path.unlink()


# SPEC-TESTER-CONV-0036
def test_empty_contracts_no_migration():
    """Empty contracts (pure signals) do not require migration."""
    contract_path = create_test_contract(
        properties={},
        aspect="exhausted"
    )

    try:
        assert contract_needs_migration(contract_path) == False
    finally:
        contract_path.unlink()


# SPEC-TESTER-CONV-0037
def test_value_objects_no_migration():
    """Value objects without id do not require migration."""
    # Test uuid value object
    contract_path = create_test_contract(
        properties={
            "value": {"type": "string", "pattern": "^[0-9a-f]{8}"}
        },
        aspect="uuid"
    )

    try:
        assert contract_needs_migration(contract_path) == False
    finally:
        contract_path.unlink()

    # Test evaluation-score value object
    contract_path = create_test_contract(
        properties={
            "score": {"type": "number"},
            "confidence": {"type": "number"}
        },
        aspect="evaluation-score"
    )

    try:
        assert contract_needs_migration(contract_path) == False
    finally:
        contract_path.unlink()


# SPEC-TESTER-CONV-0038
def test_internal_contracts_no_migration():
    """Internal contracts (transient DTOs) do not require migration."""
    contract_path = create_test_contract(
        properties={
            "player_id": {"type": "string"},
            "data": {"type": "object"}
        },
        metadata={"to": "internal"},
        aspect="dto"
    )

    try:
        assert contract_needs_migration(contract_path) == False
    finally:
        contract_path.unlink()


# SPEC-TESTER-CONV-0039
def test_explicit_persistent_flag():
    """Explicit persistence.strategy: jsonb overrides all heuristics."""
    # Event pattern BUT persistence.strategy: jsonb → needs migration
    contract_path = create_test_contract(
        properties={
            "timestamp": {"type": "string"}
        },
        metadata={"persistence": {"strategy": "jsonb"}},
        aspect="completed"  # Event pattern
    )

    try:
        assert contract_needs_migration(contract_path) == True
    finally:
        contract_path.unlink()


# SPEC-TESTER-CONV-0040
def test_explicit_non_persistent_flag():
    """Explicit persistence.strategy: none prevents migration."""
    # Has id BUT persistence.strategy: none → no migration
    contract_path = create_test_contract(
        properties={
            "id": {"type": "string"},
            "data": {"type": "object"}
        },
        metadata={"persistence": {"strategy": "none"}},
        aspect="entity"
    )

    try:
        assert contract_needs_migration(contract_path) == False
    finally:
        contract_path.unlink()


# SPEC-TESTER-CONV-0041
def test_id_overrides_event_pattern():
    """Entity with id overrides event naming pattern."""
    # Aspect is "paused" (event pattern) BUT has id → needs migration
    contract_path = create_test_contract(
        properties={
            "id": {"type": "string"},
            "session_id": {"type": "string"},
            "paused_at": {"type": "string", "format": "date-time"}
        },
        aspect="paused"
    )

    try:
        assert contract_needs_migration(contract_path) == True
    finally:
        contract_path.unlink()


# SPEC-TESTER-CONV-0042
def test_computed_aggregates_no_migration():
    """Computed aggregates without id do not require migration."""
    computed_keywords = ["computed", "calculated", "derived", "aggregated"]

    for keyword in computed_keywords:
        contract_path = create_test_contract(
            properties={
                "total": {"type": "number"},
                "count": {"type": "integer"}
            },
            description=f"This is a {keyword} result",
            aspect="stats"
        )

        try:
            assert contract_needs_migration(contract_path) == False, f"{keyword} should not require migration"
        finally:
            contract_path.unlink()


# SPEC-TESTER-CONV-0043
def test_conservative_default_external():
    """Conservative default: external contracts with properties need migration."""
    contract_path = create_test_contract(
        properties={
            "player_id": {"type": "string"},
            "score": {"type": "number"}
        },
        metadata={"to": "external"},
        aspect="profile"
    )

    try:
        assert contract_needs_migration(contract_path) == True
    finally:
        contract_path.unlink()


def test_decision_algorithm_order():
    """Test that decision rules are evaluated in correct order."""
    # Rule 1 (explicit persistence.strategy) beats Rule 5 (has id)
    contract_path = create_test_contract(
        properties={"id": {"type": "string"}},
        metadata={"persistence": {"strategy": "none"}},
        aspect="entity"
    )

    try:
        assert contract_needs_migration(contract_path) == False
    finally:
        contract_path.unlink()

    # Rule 5 (has id) beats Rule 3 (event pattern)
    contract_path = create_test_contract(
        properties={"id": {"type": "string"}},
        aspect="paused"
    )

    try:
        assert contract_needs_migration(contract_path) == True
    finally:
        contract_path.unlink()

    # Rule 2 (empty) beats everything except Rule 1
    contract_path = create_test_contract(
        properties={},
        metadata={"to": "external"},
        aspect="signal"
    )

    try:
        assert contract_needs_migration(contract_path) == False
    finally:
        contract_path.unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
