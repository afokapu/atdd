"""
Test contract and telemetry traceability reconciliation.

SPEC: .claude/agents/coach/utils.spec.yaml::traceability
IDs: SPEC-COACH-UTILS-0283 through SPEC-COACH-UTILS-0291

Validates:
- Detection of missing contract/telemetry references
- URN matching strategies (exact, normalized, path-based)
- Pragmatic fixes with user approval
- Bidirectional traceability validation
- Batch reconciliation reporting
- Clean 4-layer architecture

Architecture:
- Tests orchestrate command layer
- Command imports from atdd/coach/commands/traceability.py
- Leverages existing entities from atdd/planner/test_wagon_contract_traceability.py
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def sample_wagon_manifest():
    """Sample wagon manifest with produce items."""
    return {
        'wagon': 'generate-identifiers',
        'produce': [
            {
                'name': 'identifiers:uuid',
                'urn': 'contract:system:identifiers:uuid',
                'to': 'internal',
                'contract': None,  # Missing reference
                'telemetry': None
            },
            {
                'name': 'identifiers:username',
                'urn': 'contract:system:identifiers:username',
                'to': 'internal',
                'contract': None,  # Missing reference
                'telemetry': None
            }
        ]
    }


@pytest.fixture
def sample_contract_file():
    """Sample contract file metadata."""
    from atdd.coach.commands.traceability import ContractFile

    return ContractFile(
        file_path='contracts/commons/identifiers/uuid.schema.json',
        contract_id='system:identifiers.uuid',
        domain='system',
        resource='identifiers.uuid',
        version='1.0.0',
        producer='wagon:generate-identifiers',
        consumers=['wagon:register-account']
    )


# ============================================================================
# SPEC-COACH-UTILS-0283: Detect missing contract references
# ============================================================================


@pytest.mark.platform
def test_detect_missing_contract_references(sample_wagon_manifest, sample_contract_file):
    """
    SPEC-COACH-UTILS-0283: Detect missing contract references in wagon manifests.

    Given: Wagon manifest declares produce item with URN 'contract:system:identifiers:uuid'
    And: Contract file 'contracts/commons/identifiers/uuid.schema.json' exists
    And: Manifest has 'contract: null' for this produce item
    When: Running traceability reconciliation
    Then: Detects missing contract reference
    And: Proposes fix with actual contract file path
    And: Shows user the proposed change for approval
    """
    from atdd.coach.commands.traceability import TraceabilityReconciler

    # This will fail until implementation exists
    reconciler = TraceabilityReconciler()

    # Parse produce items
    produce_items = reconciler.parse_produce_items(sample_wagon_manifest)

    # Find contracts
    contracts = [sample_contract_file]

    # Detect missing references
    missing_refs = reconciler.detect_missing_contract_refs(produce_items, contracts)

    assert len(missing_refs) > 0
    assert missing_refs[0]['urn'] == 'contract:system:identifiers:uuid'
    assert missing_refs[0]['proposed_fix'] == 'contracts/commons/identifiers/uuid.schema.json'


# ============================================================================
# SPEC-COACH-UTILS-0284: Reconcile contract URN variations
# ============================================================================


@pytest.mark.platform
def test_reconcile_contract_urn_variations():
    """
    SPEC-COACH-UTILS-0284: Reconcile contract URN with actual file using multiple matching strategies.

    Given: Wagon produce URN 'contract:system:identifiers:uuid'
    And: Contract file with '$id' field 'system:identifiers.uuid' (dot notation)
    And: Contract file path 'contracts/commons/identifiers/uuid.schema.json'
    When: Matching URN to contract file
    Then: Tries exact match on $id
    And: Tries normalized match (colon vs dot variations)
    And: Tries path-based match
    And: Returns matching contract file
    """
    from atdd.coach.commands.traceability import ContractMatcher

    matcher = ContractMatcher()

    urn = 'contract:system:identifiers:uuid'
    contracts = [
        {
            'file_path': 'contracts/commons/identifiers/uuid.schema.json',
            'contract_id': 'system:identifiers.uuid'
        }
    ]

    # Should match despite dot vs colon notation
    matched = matcher.find_by_urn(urn, contracts)

    assert matched is not None
    assert matched['file_path'] == 'contracts/commons/identifiers/uuid.schema.json'


# ============================================================================
# SPEC-COACH-UTILS-0285: Propose and apply fix
# ============================================================================


@pytest.mark.platform
def test_propose_and_apply_contract_fix(tmp_path):
    """
    SPEC-COACH-UTILS-0285: Propose fix for missing contract reference with user approval.

    Given: Missing contract reference detected
    And: Contract file path 'contracts/commons/identifiers/uuid.schema.json'
    And: Wagon manifest at 'plan/generate_identifiers/_generate_identifiers.yaml'
    When: User approves fix
    Then: Updates wagon manifest YAML file
    And: Changes 'contract: null' to 'contract: contracts/commons/identifiers/uuid.schema.json'
    And: Preserves YAML formatting and structure
    And: Logs change to facts/audit.log
    """
    from atdd.coach.commands.traceability import TraceabilityFixer

    # Create temporary manifest file
    manifest_file = tmp_path / "test_manifest.yaml"
    manifest_content = """wagon: generate-identifiers
produce:
- name: identifiers:uuid
  urn: contract:system:identifiers:uuid
  to: internal
  contract: null
  telemetry: null
"""
    manifest_file.write_text(manifest_content)

    fixer = TraceabilityFixer()

    # Apply fix
    fix_applied = fixer.apply_contract_fix(
        manifest_path=str(manifest_file),
        produce_name='identifiers:uuid',
        contract_path='contracts/commons/identifiers/uuid.schema.json'
    )

    assert fix_applied is True

    # Verify file was updated
    updated_content = manifest_file.read_text()
    assert 'contract: contracts/commons/identifiers/uuid.schema.json' in updated_content
    assert 'contract: null' not in updated_content


# ============================================================================
# SPEC-COACH-UTILS-0286: Validate bidirectional traceability
# ============================================================================


@pytest.mark.platform
def test_validate_bidirectional_traceability():
    """
    SPEC-COACH-UTILS-0286: Validate bidirectional traceability between wagon and contract.

    Given: Wagon 'generate-identifiers' declares producing 'contract:system:identifiers:uuid'
    And: Contract file has 'x-artifact-metadata.producer: wagon:generate-identifiers'
    When: Validating bidirectional references
    Then: Confirms wagon->contract reference exists
    And: Confirms contract->wagon reference matches
    And: Reports as fully traced
    """
    from atdd.coach.commands.traceability import TraceabilityValidator

    validator = TraceabilityValidator()

    produce_item = {
        'wagon': 'generate-identifiers',
        'urn': 'contract:system:identifiers:uuid'
    }

    contract = {
        'file_path': 'contracts/commons/identifiers/uuid.schema.json',
        'producer': 'wagon:generate-identifiers'
    }

    is_bidirectional = validator.validate_bidirectional(produce_item, contract)

    assert is_bidirectional is True


# ============================================================================
# SPEC-COACH-UTILS-0287: Detect mismatched producer
# ============================================================================


@pytest.mark.platform
def test_detect_mismatched_producer():
    """
    SPEC-COACH-UTILS-0287: Detect mismatched producer in contract metadata.

    Given: Wagon 'generate-identifiers' declares producing 'contract:system:identifiers:uuid'
    And: Contract file has 'x-artifact-metadata.producer: wagon:other-wagon'
    When: Validating producer consistency
    Then: Detects mismatch between wagon declaration and contract metadata
    And: Reports as traceability violation
    And: Proposes correction to either wagon or contract
    """
    from atdd.coach.commands.traceability import TraceabilityValidator

    validator = TraceabilityValidator()

    produce_item = {
        'wagon': 'generate-identifiers',
        'urn': 'contract:system:identifiers:uuid'
    }

    contract = {
        'file_path': 'contracts/commons/identifiers/uuid.schema.json',
        'producer': 'wagon:other-wagon'  # Mismatch!
    }

    mismatch = validator.check_producer_match(produce_item, contract)

    assert mismatch is not None
    assert mismatch['expected'] == 'wagon:generate-identifiers'
    assert mismatch['actual'] == 'wagon:other-wagon'


# ============================================================================
# SPEC-COACH-UTILS-0288: Batch reconciliation report
# ============================================================================


@pytest.mark.platform
def test_batch_reconciliation_report():
    """
    SPEC-COACH-UTILS-0288: Batch reconciliation report for all wagons.

    Given: Multiple wagon manifests in plan/ directory
    And: Multiple contract files in contracts/ directory
    And: Some with missing references, some with mismatches
    When: Running full repository reconciliation
    Then: Scans all wagon manifests
    And: Scans all contract files
    And: Groups issues by wagon
    And: Shows statistics (total issues, by type)
    And: Provides prioritized fix list
    """
    from atdd.coach.commands.traceability import TraceabilityReconciler

    reconciler = TraceabilityReconciler()

    # This will scan the actual repo
    report = reconciler.reconcile_all()

    # reconcile_all() returns ReconciliationResult object
    assert hasattr(report, 'total_issues')
    assert hasattr(report, 'missing_contract_refs')
    assert hasattr(report, 'by_wagon')
    assert isinstance(report.total_issues, int)


# ============================================================================
# SPEC-COACH-UTILS-0289: Support telemetry reconciliation
# ============================================================================


@pytest.mark.platform
def test_detect_missing_telemetry_references():
    """
    SPEC-COACH-UTILS-0289: Support telemetry reference reconciliation.

    Given: Wagon manifest declares produce item with telemetry URN
    And: Telemetry file exists in telemetry/ directory
    And: Manifest has 'telemetry: null' for this produce item
    When: Running traceability reconciliation
    Then: Detects missing telemetry reference
    And: Proposes fix with actual telemetry file path
    And: Applies same reconciliation logic as contracts
    """
    from atdd.coach.commands.traceability import TraceabilityReconciler

    reconciler = TraceabilityReconciler()

    wagon_manifest = {
        'wagon': 'generate-identifiers',
        'produce': [
            {
                'name': 'uuid-generation-metrics',
                'urn': 'telemetry:metric:be:uuid:generation:duration',
                'to': 'internal',
                'contract': None,
                'telemetry': None  # Missing reference
            }
        ]
    }

    from atdd.coach.commands.traceability import TelemetryFile

    telemetry_files = [
        TelemetryFile(
            file_path='telemetry/metrics/be/uuid/generation_duration.yaml',
            telemetry_id='telemetry:metric:be:uuid:generation:duration',
            domain='metric',
            resource='be.uuid.generation.duration',
            producer='wagon:generate-identifiers'
        )
    ]

    produce_items = reconciler.parse_produce_items(wagon_manifest)
    missing_refs = reconciler.detect_missing_telemetry_refs(produce_items, telemetry_files)

    assert len(missing_refs) > 0
    assert missing_refs[0]['proposed_fix'] == 'telemetry/metrics/be/uuid/generation_duration.yaml'


# ============================================================================
# SPEC-COACH-UTILS-0290: Leverage existing test diagnostics
# ============================================================================


@pytest.mark.platform
def test_leverage_existing_test_diagnostics():
    """
    SPEC-COACH-UTILS-0290: Leverage existing test diagnostics from test_wagon_contract_traceability.

    Given: Existing test file 'atdd/planner/test_wagon_contract_traceability.py'
    And: Test provides detailed reconciliation entities and use cases
    When: Running traceability command
    Then: Imports and uses WagonManifest, ContractFile, ProduceItem entities
    And: Imports and uses ManifestParser, ContractFinder use cases
    And: Avoids code duplication
    And: Reuses proven diagnostic logic
    """
    # Verify we can import from existing test file
    # This demonstrates code reuse
    try:
        # The implementation should import from this module
        from atdd.coach.commands.traceability import TraceabilityReconciler

        # Verify the reconciler uses shared entities
        reconciler = TraceabilityReconciler()

        # Check that it has methods that align with existing diagnostic logic
        assert hasattr(reconciler, 'parse_produce_items')
        assert hasattr(reconciler, 'detect_missing_contract_refs')

    except ImportError:
        pytest.fail("Implementation should import from test diagnostic module")


# ============================================================================
# SPEC-COACH-UTILS-0291: Clean 4-layer architecture
# ============================================================================


@pytest.mark.platform
def test_clean_architecture_layers():
    """
    SPEC-COACH-UTILS-0291: Clean 4-layer architecture with entities, use cases, adapters, commands.

    Given: Traceability command implementation
    When: Refactoring for clean architecture
    Then: Layer 1 (Entities) - ProduceItem, ContractFile, ReconciliationResult
    And: Layer 2 (Use Cases) - ManifestParser, ContractFinder, TraceabilityReconciler
    And: Layer 3 (Adapters) - ReportFormatter, YAMLUpdater
    And: Layer 4 (Command) - CLI entry point, user interaction, orchestration
    And: Each layer depends only on inner layers
    And: Business logic isolated from I/O
    """
    from atdd.coach.commands.traceability import (
        # Layer 1: Entities
        ProduceItem,
        ContractFile,
        ReconciliationResult,

        # Layer 2: Use Cases
        ManifestParser,
        ContractFinder,
        TraceabilityReconciler,

        # Layer 3: Adapters
        ReportFormatter,
        YAMLUpdater
    )

    # Verify entities are dataclasses (immutable domain models)
    assert hasattr(ProduceItem, '__dataclass_fields__')
    assert hasattr(ContractFile, '__dataclass_fields__')
    assert hasattr(ReconciliationResult, '__dataclass_fields__')

    # Verify use cases have business logic methods
    parser = ManifestParser()
    assert callable(getattr(parser, 'parse_manifest', None))

    finder = ContractFinder()
    assert callable(getattr(finder, 'find_by_urn', None))

    reconciler = TraceabilityReconciler()
    assert callable(getattr(reconciler, 'reconcile_all', None))

    # Verify adapters have presentation/I/O methods
    formatter = ReportFormatter()
    assert callable(getattr(formatter, 'format_report', None))

    updater = YAMLUpdater()
    assert callable(getattr(updater, 'update_yaml_field', None))
