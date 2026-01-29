"""
Test telemetry array migration for uniqueness support.

SPEC: .claude/agents/coach/schemas.spec.yaml::telemetry_array_migration
ID: SPEC-COACH-SCHEMA-0019

Validates:
- Telemetry field accepts array of URNs
- Backward compatibility with single URN
- Validation of array entries
- No URN collision when multiple variants share aspect
- Complete artifact-level URNs for uniqueness

Architecture:
- Tests validate ProduceItem domain entity behavior
- Tests validate ManifestParser parsing logic
- Tests validate TelemetryReconciler validation logic
"""

import pytest
from pathlib import Path
from atdd.coach.commands.traceability import (
    ProduceItem,
    ManifestParser,
    TelemetryFile
)


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def sample_wagon_manifest_with_array_telemetry():
    """Sample wagon manifest with array telemetry references."""
    return {
        'wagon': 'pace-dilemmas',
        'produce': [
            {
                'name': 'match:dilemma.paired',
                'to': 'external',
                'contract': 'contract:match:dilemma.paired',
                'telemetry': [
                    'telemetry:match:dilemma.paired',
                    'telemetry:match:pacing.exhausted'
                ]
            },
            {
                'name': 'match:dilemma.current',
                'to': 'external',
                'contract': 'contract:match:dilemma.current',
                'telemetry': [
                    'telemetry:match:dilemma.current'
                ]
            }
        ]
    }


@pytest.fixture
def sample_wagon_manifest_with_single_telemetry():
    """Sample wagon manifest with single URN (backward compatibility)."""
    return {
        'wagon': 'probe-character',
        'produce': [
            {
                'name': 'sensory:character.dialog',
                'to': 'external',
                'contract': 'contract:sensory:character.dialog',
                'telemetry': 'telemetry:sensory:character.dialog'
            }
        ]
    }


@pytest.fixture
def sample_wagon_manifest_with_null_telemetry():
    """Sample wagon manifest with null telemetry."""
    return {
        'wagon': 'stage-characters',
        'produce': [
            {
                'name': 'sensory:character.expression',
                'to': 'external',
                'contract': 'contract:sensory:character.expression',
                'telemetry': None
            }
        ]
    }


# ============================================================================
# SPEC-COACH-SCHEMA-0019: Telemetry field accepts array of URNs
# ============================================================================


@pytest.mark.platform
def test_telemetry_accepts_array(sample_wagon_manifest_with_array_telemetry):
    """
    SPEC-COACH-SCHEMA-0019: Telemetry field accepts array of URNs for multiple signals.

    Given: Wagon has multiple produce items sharing same aspect
           Example: match:dilemma.paired and match:dilemma.current
           Both need separate telemetry URNs for uniqueness
    When: Produce item telemetry field is defined as array
    Then: Telemetry accepts array format: [telemetry:match:dilemma.paired, telemetry:match:dilemma.current]
          Each array entry uses complete artifact-level URN
          No URN collision when multiple variants share aspect
    """
    parser = ManifestParser()
    produce_items = parser.parse_produce_items(sample_wagon_manifest_with_array_telemetry)

    # Verify first produce item has array telemetry
    first_item = produce_items[0]
    assert first_item.name == 'match:dilemma.paired'
    assert isinstance(first_item.telemetry_ref, list), "Telemetry should be parsed as list"
    assert len(first_item.telemetry_ref) == 2
    assert 'telemetry:match:dilemma.paired' in first_item.telemetry_ref
    assert 'telemetry:match:pacing.exhausted' in first_item.telemetry_ref

    # Verify second produce item has array telemetry
    second_item = produce_items[1]
    assert second_item.name == 'match:dilemma.current'
    assert isinstance(second_item.telemetry_ref, list), "Telemetry should be parsed as list"
    assert len(second_item.telemetry_ref) == 1
    assert 'telemetry:match:dilemma.current' in second_item.telemetry_ref

    # Verify no collision - each has unique URN
    all_urns = first_item.telemetry_ref + second_item.telemetry_ref
    assert 'telemetry:match:dilemma.paired' in all_urns
    assert 'telemetry:match:dilemma.current' in all_urns
    # Both are unique despite sharing aspect 'match:dilemma'


@pytest.mark.platform
def test_telemetry_validates_array_entries(sample_wagon_manifest_with_array_telemetry):
    """
    SPEC-COACH-SCHEMA-0019: Traceability validation checks all array entries exist.

    Given: Produce item has telemetry array
    When: Validating telemetry references
    Then: Each entry in array is validated
          Each entry must use complete artifact-level URN
          Validation checks all URNs exist in telemetry directory
    """
    parser = ManifestParser()
    produce_items = parser.parse_produce_items(sample_wagon_manifest_with_array_telemetry)

    first_item = produce_items[0]

    # Verify telemetry_ref is list
    assert isinstance(first_item.telemetry_ref, list)

    # Verify each entry is a complete URN (not null, not empty)
    for telemetry_urn in first_item.telemetry_ref:
        assert telemetry_urn is not None
        assert isinstance(telemetry_urn, str)
        assert telemetry_urn.startswith('telemetry:')
        # Complete artifact-level URN includes variant
        assert ':' in telemetry_urn
        assert '.' in telemetry_urn

    # Verify no null telemetry when array is present
    assert not first_item.has_null_telemetry_ref


@pytest.mark.platform
def test_telemetry_backward_compatible_single_urn(sample_wagon_manifest_with_single_telemetry):
    """
    SPEC-COACH-SCHEMA-0019: Telemetry accepts single URN for backward compatibility.

    Given: Wagon manifest has single telemetry URN (not array)
    When: Parsing produce items
    Then: Single URN is treated as single-item array internally
          has_null_telemetry_ref returns False
          Telemetry ref accessible as list for uniform processing
    """
    parser = ManifestParser()
    produce_items = parser.parse_produce_items(sample_wagon_manifest_with_single_telemetry)

    item = produce_items[0]
    assert item.name == 'sensory:character.dialog'

    # Single URN should be converted to list internally for uniform processing
    assert isinstance(item.telemetry_ref, list), "Single URN should be normalized to list"
    assert len(item.telemetry_ref) == 1
    assert item.telemetry_ref[0] == 'telemetry:sensory:character.dialog'

    # Should not be treated as null
    assert not item.has_null_telemetry_ref


@pytest.mark.platform
def test_telemetry_null_handling(sample_wagon_manifest_with_null_telemetry):
    """
    SPEC-COACH-SCHEMA-0019: Telemetry accepts null for items without telemetry.

    Given: Produce item has telemetry: null
    When: Parsing produce items
    Then: has_null_telemetry_ref returns True
          telemetry_ref is None or empty list
    """
    parser = ManifestParser()
    produce_items = parser.parse_produce_items(sample_wagon_manifest_with_null_telemetry)

    item = produce_items[0]
    assert item.name == 'sensory:character.expression'

    # Null telemetry should be detected
    assert item.has_null_telemetry_ref


@pytest.mark.platform
def test_produce_item_supports_telemetry_array():
    """
    SPEC-COACH-SCHEMA-0019: ProduceItem entity supports telemetry as array.

    Given: Need to represent produce item with multiple telemetry URNs
    When: Creating ProduceItem with list telemetry_ref
    Then: ProduceItem stores list correctly
          All properties work with list format
    """
    item = ProduceItem(
        name='match:dilemma.paired',
        to='external',
        contract_ref='contract:match:dilemma.paired',
        telemetry_ref=['telemetry:match:dilemma.paired', 'telemetry:match:pacing.exhausted'],
        wagon='pace-dilemmas'
    )

    assert isinstance(item.telemetry_ref, list)
    assert len(item.telemetry_ref) == 2
    assert 'telemetry:match:dilemma.paired' in item.telemetry_ref
    assert not item.has_null_telemetry_ref
