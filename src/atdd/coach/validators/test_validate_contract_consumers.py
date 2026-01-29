"""
SPEC-COACH-UTILS-0292: Detect consumer mismatches between wagon manifests and contract schemas
SPEC-COACH-UTILS-0293: Apply consumer synchronization updates with user approval

Tests validation and synchronization of consumer declarations between:
- Wagon manifests (plan/*/_*.yaml)
- Feature manifests (plan/*/*/*.yaml)
- Contract schemas (contracts/**/*.schema.json)
"""
import pytest
import yaml
import json
from pathlib import Path


@pytest.mark.platform
def test_detect_consumer_mismatches(tmp_path):
    """
    SPEC-COACH-UTILS-0292: Detect consumer mismatches between wagon manifests and contract schemas

    Given: Wagon manifests exist at plan/*/_*.yaml with optional consumers field
           Feature manifests exist at plan/*/*/*.yaml with optional consumers field
           Contract schemas exist at contracts/**/*.schema.json with x-artifact-metadata.consumers
           Consumers in wagon manifests reference contracts as contract:domain:resource
           Consumers in contract schemas follow pattern wagon:name or external:service
           Some manifests may declare consumers that contracts don't list
           Some contracts may list consumers that manifests don't declare
    When: Running consumer validation between manifests and contracts
    Then: All wagon manifests are scanned for consumer declarations
          All feature manifests are scanned for consumer declarations
          All contract schemas are scanned for x-artifact-metadata.consumers
          Mismatches are detected in both directions
          Direction 1 manifest→contract shows wagons/features declaring contracts not listing them as consumers
          Direction 2 contract→manifest shows contracts listing wagon consumers not declared in manifest
          Report shows three fix options 1-update manifests only 2-update contracts only 3-mutual sync both
          No changes applied without user approval
    """
    # Setup test directories
    plan_dir = tmp_path / "plan"
    plan_dir.mkdir()
    contracts_dir = tmp_path / "contracts"
    contracts_dir.mkdir()

    # Create wagon manifest that declares consuming a contract
    wagon_dir = plan_dir / "test_wagon"
    wagon_dir.mkdir()
    wagon_manifest = wagon_dir / "_test_wagon.yaml"
    wagon_data = {
        "wagon": "test-wagon",
        "description": "Test wagon",
        "consume": [
            {"name": "contract:match:dilemma.current"}
        ]
    }
    with open(wagon_manifest, 'w') as f:
        yaml.dump(wagon_data, f, default_flow_style=False, sort_keys=False)

    # Create feature manifest that declares consuming a contract
    features_dir = wagon_dir / "features"
    features_dir.mkdir()
    feature_manifest = features_dir / "choose_option.yaml"
    feature_data = {
        "feature": "choose-option",
        "description": "Choose dilemma option",
        "consume": [
            {"name": "contract:match:dilemma.paired"}
        ]
    }
    with open(feature_manifest, 'w') as f:
        yaml.dump(feature_data, f, default_flow_style=False, sort_keys=False)

    # Create contract that DOES list the wagon as consumer (should match)
    dilemma_dir = contracts_dir / "dilemma"
    dilemma_dir.mkdir()
    current_contract = dilemma_dir / "current.schema.json"
    current_data = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "$id": "match:dilemma.current",
        "title": "CurrentDilemma",
        "description": "Current dilemma contract",
        "type": "object",
        "x-artifact-metadata": {
            "domain": "dilemma",
            "resource": "current",
            "api": {"method": "GET", "path": "/dilemmas/current"},
            "producer": "wagon:pace-dilemmas",
            "consumers": ["wagon:test-wagon"],  # Matches wagon manifest
            "dependencies": [],
            "traceability": {
                "wagon_ref": "plan/pace_dilemmas/_pace_dilemmas.yaml",
                "feature_refs": ["feature:pace-dilemmas:select-dilemma"]
            },
            "testing": {
                "directory": "contracts/dilemma/tests/",
                "schema_tests": ["current_schema_test.json"]
            }
        }
    }
    with open(current_contract, 'w') as f:
        json.dump(current_data, f, indent=2)

    # Create contract that DOES NOT list the feature as consumer (mismatch)
    paired_contract = dilemma_dir / "paired.schema.json"
    paired_data = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "$id": "match:dilemma.paired",
        "title": "PairedDilemma",
        "description": "Paired dilemma contract",
        "type": "object",
        "x-artifact-metadata": {
            "domain": "dilemma",
            "resource": "paired",
            "api": {"method": "GET", "path": "/dilemmas/paired"},
            "producer": "wagon:pace-dilemmas",
            "consumers": [],  # MISSING wagon:test-wagon - this is a mismatch!
            "dependencies": [],
            "traceability": {
                "wagon_ref": "plan/pace_dilemmas/_pace_dilemmas.yaml",
                "feature_refs": ["feature:pace-dilemmas:pair-fragments"]
            },
            "testing": {
                "directory": "contracts/dilemma/tests/",
                "schema_tests": ["paired_schema_test.json"]
            }
        }
    }
    with open(paired_contract, 'w') as f:
        json.dump(paired_data, f, indent=2)

    # Create contract that lists a consumer not declared in any manifest (reverse mismatch)
    ux_dir = contracts_dir / "ux"
    ux_dir.mkdir()
    foundations_dir = ux_dir / "foundations"
    foundations_dir.mkdir()
    color_contract = foundations_dir / "color.schema.json"
    color_data = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "$id": "ux:foundations",
        "title": "ColorFoundations",
        "description": "Color foundations contract",
        "type": "object",
        "x-artifact-metadata": {
            "domain": "ux",
            "resource": "foundations",
            "collection": True,
            "member": "color",
            "api": {"method": "GET", "path": "/ux/foundations/color"},
            "producer": "wagon:maintain-ux",
            "consumers": ["wagon:nonexistent-wagon"],  # Not declared in any manifest!
            "dependencies": [],
            "traceability": {
                "wagon_ref": "plan/maintain_ux/_maintain_ux.yaml",
                "feature_refs": ["feature:maintain-ux:design-tokens"]
            },
            "testing": {
                "directory": "contracts/commons/ux/foundations/tests/",
                "schema_tests": ["color_schema_test.json"]
            }
        }
    }
    with open(color_contract, 'w') as f:
        json.dump(color_data, f, indent=2)

    # Import the validator (will be implemented)
    from atdd.coach.commands.consumers import ConsumerValidator

    # Run validation
    validator = ConsumerValidator(tmp_path)
    report = validator.detect_mismatches()

    # Assertions - check that mismatches were detected
    assert "manifest_to_contract" in report, "Should detect manifest→contract mismatches"
    assert "contract_to_manifest" in report, "Should detect contract→manifest mismatches"

    # Check manifest→contract mismatch (feature declares contract:match:dilemma.paired but contract doesn't list it)
    manifest_to_contract = report["manifest_to_contract"]
    assert len(manifest_to_contract) == 1, "Should find 1 manifest→contract mismatch"
    mismatch = manifest_to_contract[0]
    assert mismatch["manifest"] == str(feature_manifest.relative_to(tmp_path))
    assert mismatch["contract"] == "contract:match:dilemma.paired"
    assert "dilemma/paired.schema.json" in mismatch["contract_file"]

    # Check contract→manifest mismatch (contract lists wagon:nonexistent-wagon but no manifest declares it)
    contract_to_manifest = report["contract_to_manifest"]
    assert len(contract_to_manifest) == 1, "Should find 1 contract→manifest mismatch"
    mismatch = contract_to_manifest[0]
    assert "ux/foundations/color.schema.json" in mismatch["contract_file"]
    assert mismatch["consumer"] == "wagon:nonexistent-wagon"

    # Verify no changes were made (validation only)
    with open(paired_contract, 'r') as f:
        unchanged_contract = json.load(f)
    assert unchanged_contract["x-artifact-metadata"]["consumers"] == [], "Contract should be unchanged"


@pytest.mark.platform
def test_apply_consumer_sync_updates(tmp_path):
    """
    SPEC-COACH-UTILS-0293: Apply consumer synchronization updates with user approval

    Given: Consumer mismatches detected between manifests and contracts
           User has selected fix direction 1-manifests 2-contracts 3-mutual
           Target files exist and are valid YAML/JSON
    When: Applying consumer synchronization updates
    Then: If option 1 adds missing consumer references to wagon manifests only
          If option 2 adds missing consumers to contract x-artifact-metadata.consumers only
          If option 3 syncs both directions adding to manifests and contracts
          Wagon manifest updates add contract references in format contract:domain:resource
          Contract schema updates add consumers in format wagon:name or external:service
          All updates preserve existing consumers no duplicates added
          Updated files validate against respective schemas
          YAML and JSON formatting preserved
          Summary report shows all applied changes
    """
    # Setup test directories
    plan_dir = tmp_path / "plan"
    plan_dir.mkdir()
    contracts_dir = tmp_path / "contracts"
    contracts_dir.mkdir()

    # Create feature manifest missing consumer declaration
    wagon_dir = plan_dir / "test_wagon"
    wagon_dir.mkdir()
    features_dir = wagon_dir / "features"
    features_dir.mkdir()
    feature_manifest = features_dir / "choose_option.yaml"
    feature_data = {
        "feature": "choose-option",
        "description": "Choose dilemma option",
        "consume": []  # Empty - will be updated
    }
    with open(feature_manifest, 'w') as f:
        yaml.dump(feature_data, f, default_flow_style=False, sort_keys=False)

    # Create contract missing consumer in metadata
    dilemma_dir = contracts_dir / "dilemma"
    dilemma_dir.mkdir()
    current_contract = dilemma_dir / "current.schema.json"
    current_data = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "$id": "match:dilemma.current",
        "title": "CurrentDilemma",
        "description": "Current dilemma contract",
        "type": "object",
        "x-artifact-metadata": {
            "domain": "dilemma",
            "resource": "current",
            "api": {"method": "GET", "path": "/dilemmas/current"},
            "producer": "wagon:pace-dilemmas",
            "consumers": [],  # Empty - will be updated
            "dependencies": [],
            "traceability": {
                "wagon_ref": "plan/pace_dilemmas/_pace_dilemmas.yaml",
                "feature_refs": ["feature:pace-dilemmas:select-dilemma"]
            },
            "testing": {
                "directory": "contracts/dilemma/tests/",
                "schema_tests": ["current_schema_test.json"]
            }
        }
    }
    with open(current_contract, 'w') as f:
        json.dump(current_data, f, indent=2)

    # Import the validator
    from atdd.coach.commands.consumers import ConsumerValidator

    validator = ConsumerValidator(tmp_path)

    # Test option 3: Mutual sync (both directions)
    updates = [
        {
            "type": "manifest_to_contract",
            "manifest_file": str(feature_manifest),
            "contract_file": str(current_contract),
            "contract_ref": "contract:match:dilemma.current",
            "consumer_ref": "wagon:test-wagon"
        }
    ]

    summary = validator.apply_updates(updates, direction="mutual")

    # Verify manifest was updated
    with open(feature_manifest, 'r') as f:
        updated_feature = yaml.safe_load(f)
    assert len(updated_feature["consume"]) == 1, "Feature should have 1 consumer"
    assert updated_feature["consume"][0]["name"] == "contract:match:dilemma.current"

    # Verify contract was updated
    with open(current_contract, 'r') as f:
        updated_contract = json.load(f)
    assert len(updated_contract["x-artifact-metadata"]["consumers"]) == 1
    assert "wagon:test-wagon" in updated_contract["x-artifact-metadata"]["consumers"]

    # Verify summary report
    assert "applied" in summary
    assert summary["applied"] == 2  # Both manifest and contract updated
