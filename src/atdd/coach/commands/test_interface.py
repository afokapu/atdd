"""
SPEC-COACH-UTILS-0294: Generate complete contract metadata from wagon and feature interfaces
SPEC-COACH-UTILS-0295: Validate and update existing contract metadata completeness
SPEC-COACH-UTILS-0296: Create placeholder test files for scaffolded contracts

Tests the contract scaffold generation automation that reads wagon/feature interfaces
and auto-generates contract metadata following artifact-naming.convention.yaml.
"""
import pytest
import yaml
import json
from pathlib import Path


@pytest.mark.platform
def test_scaffold_contract_metadata_from_wagon_and_feature_interfaces(tmp_path):
    """
    SPEC-COACH-UTILS-0294: Generate complete contract metadata from wagon and feature interfaces

    Given: A contract artifact URN following artifact-naming.convention.yaml
           Wagon manifests exist at plan/*/_*.yaml with produce[] and consume[] arrays
           Feature manifests exist at plan/{wagon}/features/*.yaml with produces[] arrays
           Artifact URN uses colon for hierarchy and dot for variant
           Contract may or may not exist at derived file path from artifact URN
    When: Scaffolding contract metadata from wagon and feature interfaces
    Then: Parse artifact URN according to convention pattern theme(category)*aspect(.variant)?
          Split URN by colons and dots to extract theme hierarchy aspect and variant
          Convert artifact URN to contract file path using convention mapping
          Scan all wagon manifests produce[] to find producer wagon
          Cross-check producer wagon features[] produces[] arrays match wagon produce[]
          Scan all wagon manifests consume[] to find consumer wagons
          Extract dependencies from producer wagon consume[] array
          Infer API method from aspect and variant patterns
          Generate API path by joining theme hierarchy aspect with slashes
          Extract traceability wagon_ref from producer wagon file path
          Extract traceability feature_refs from producer wagon features[] URNs
          Generate testing directory path and placeholder test file name
          Create full contract scaffold with x-artifact-metadata
    """
    # Setup test directories
    plan_dir = tmp_path / "plan"
    plan_dir.mkdir()
    contracts_dir = tmp_path / "contracts"
    contracts_dir.mkdir()
    convention_dir = tmp_path / ".claude" / "conventions" / "planner"
    convention_dir.mkdir(parents=True)

    # Create artifact naming convention file
    convention_data = {
        "version": "2.1",
        "name": "Artifact Naming Convention",
        "naming_pattern": {
            "full_pattern": "{theme}(:{category})*:{aspect}(.{variant})?"
        }
    }
    with open(convention_dir / "artifact-naming.convention.yaml", 'w') as f:
        yaml.dump(convention_data, f)

    # Create producer wagon that produces mechanic:timebank.exhausted
    burn_timebank_dir = plan_dir / "burn_timebank"
    burn_timebank_dir.mkdir()
    wagon_manifest = burn_timebank_dir / "_burn_timebank.yaml"
    wagon_data = {
        "wagon": "burn-timebank",
        "theme": "mechanic",
        "produce": [
            {"name": "mechanic:timebank.exhausted", "contract": "contract:mechanic:timebank.exhausted"}
        ],
        "consume": [
            {"name": "contract:match:state.committed"}
        ],
        "features": [
            {"name": "feature:burn-timebank:exhaust-timer"}
        ]
    }
    with open(wagon_manifest, 'w') as f:
        yaml.dump(wagon_data, f, default_flow_style=False, sort_keys=False)

    # Create feature manifest that matches wagon produce
    features_dir = burn_timebank_dir / "features"
    features_dir.mkdir()
    feature_manifest = features_dir / "exhaust_timer.yaml"
    feature_data = {
        "urn": "feature:burn-timebank:exhaust-timer",
        "feature": "exhaust-timer",
        "description": "Exhaust timebank timer",
        "produces": [
            {"name": "mechanic:timebank.exhausted", "contract": "contract:mechanic:timebank.exhausted"}
        ]
    }
    with open(feature_manifest, 'w') as f:
        yaml.dump(feature_data, f, default_flow_style=False, sort_keys=False)

    # Create consumer wagon
    reveal_status_dir = plan_dir / "reveal_status"
    reveal_status_dir.mkdir()
    consumer_manifest = reveal_status_dir / "_reveal_status.yaml"
    consumer_data = {
        "wagon": "reveal-status",
        "theme": "sensory",
        "consume": [
            {"name": "contract:mechanic:timebank.exhausted"}
        ]
    }
    with open(consumer_manifest, 'w') as f:
        yaml.dump(consumer_data, f, default_flow_style=False, sort_keys=False)

    # Import the scaffold function
    from atdd.coach.commands.interface import scaffold_contract_metadata

    # Execute scaffold generation
    artifact_urn = "mechanic:timebank.exhausted"
    result = scaffold_contract_metadata(
        artifact_urn=artifact_urn,
        plan_dir=plan_dir,
        contracts_dir=contracts_dir,
        convention_path=convention_dir / "artifact-naming.convention.yaml"
    )

    # Verify contract was created at correct path
    expected_path = contracts_dir / "mechanic" / "timebank" / "exhausted.schema.json"
    assert expected_path.exists(), f"Contract not created at {expected_path}"

    # Read and verify contract content
    with open(expected_path) as f:
        contract = json.load(f)

    # Verify x-artifact-metadata structure
    metadata = contract.get("x-artifact-metadata", {})

    # Verify domain and resource parsed from URN
    assert metadata["domain"] == "timebank", "Domain should be 'timebank'"
    assert metadata["resource"] == "timebank.exhausted", "Resource should be 'timebank.exhausted'"

    # Verify version
    assert metadata["version"] == "1.0.0", "Version should default to 1.0.0"

    # Verify producer from wagon
    assert metadata["producer"] == "wagon:burn-timebank", "Producer should be burn-timebank wagon"

    # Verify consumers scanned from all wagons
    assert "wagon:reveal-status" in metadata["consumers"], "Should find reveal-status as consumer"

    # Verify dependencies from producer wagon consume[]
    assert "contract:match:state.committed" in metadata["dependencies"], "Should extract dependencies"

    # Verify API inferred from resource pattern (exhausted = event = POST)
    api = metadata.get("api", {})
    operations = api.get("operations", [])
    assert len(operations) > 0, "Should have API operations"
    assert operations[0]["method"] == "POST", "Exhausted event should be POST"
    assert operations[0]["path"] == "/mechanic/timebank/exhausted", "Path should be /mechanic/timebank/exhausted"

    # Verify traceability
    traceability = metadata.get("traceability", {})
    assert traceability["wagon_ref"] == "plan/burn_timebank/_burn_timebank.yaml", "Wagon ref should match"
    assert "feature:burn-timebank:exhaust-timer" in traceability["feature_refs"], "Feature ref should match"

    # Verify testing paths
    testing = metadata.get("testing", {})
    assert testing["directory"] == "contracts/mechanic/timebank/tests/", "Test directory should be correct"
    assert "exhausted_schema_test.json" in testing["schema_tests"], "Test file should be exhausted_schema_test.json"

    # Verify result summary
    assert result["created"] == True, "Contract should be marked as created"
    assert result["path"] == str(expected_path), "Result should contain path"


@pytest.mark.platform
def test_validate_and_update_existing_contract_metadata(tmp_path):
    """
    SPEC-COACH-UTILS-0295: Validate and update existing contract metadata completeness

    Given: Contract schema exists with x-artifact-metadata section but may be incomplete
           Wagon manifests have changed since contract was created
           New consumers or dependencies may have been added
    When: Validating and updating existing contract metadata
    Then: Read existing contract x-artifact-metadata section
          Re-scan wagon manifests to build complete metadata from current state
          Compare existing metadata with generated metadata
          Detect missing or outdated fields
          Update only missing or outdated fields preserve user customizations
          Do not overwrite manually edited fields
          Validate updated contract against JSON Schema spec
          Report what was updated and why
    """
    # Setup test directories
    plan_dir = tmp_path / "plan"
    plan_dir.mkdir()
    contracts_dir = tmp_path / "contracts"
    contracts_dir.mkdir()

    # Create producer wagon
    pace_dilemmas_dir = plan_dir / "pace_dilemmas"
    pace_dilemmas_dir.mkdir()
    wagon_manifest = pace_dilemmas_dir / "_pace_dilemmas.yaml"
    wagon_data = {
        "wagon": "pace-dilemmas",
        "theme": "match",
        "produce": [
            {"name": "match:dilemma.current", "contract": "contract:match:dilemma.current"}
        ]
    }
    with open(wagon_manifest, 'w') as f:
        yaml.dump(wagon_data, f, default_flow_style=False, sort_keys=False)

    # Create NEW consumer wagon (added after contract was created)
    resolve_dilemmas_dir = plan_dir / "resolve_dilemmas"
    resolve_dilemmas_dir.mkdir()
    consumer_manifest = resolve_dilemmas_dir / "_resolve_dilemmas.yaml"
    consumer_data = {
        "wagon": "resolve-dilemmas",
        "theme": "mechanic",
        "consume": [
            {"name": "contract:match:dilemma.current"}
        ]
    }
    with open(consumer_manifest, 'w') as f:
        yaml.dump(consumer_data, f, default_flow_style=False, sort_keys=False)

    # Create EXISTING contract with INCOMPLETE metadata (missing new consumer)
    dilemma_dir = contracts_dir / "match" / "dilemma"
    dilemma_dir.mkdir(parents=True)
    existing_contract = dilemma_dir / "current.schema.json"
    contract_data = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "$id": "match:dilemma.current",
        "version": "1.0.0",
        "title": "Current Dilemma Contract",
        "description": "CUSTOM DESCRIPTION - should not be overwritten",
        "type": "object",
        "properties": {
            "id": {"type": "string"}
        },
        "x-artifact-metadata": {
            "domain": "dilemma",
            "resource": "dilemma.current",
            "version": "1.0.0",
            "producer": "wagon:pace-dilemmas",
            "consumers": [],  # INCOMPLETE - missing new consumer
            "dependencies": [],
            "api": {
                "operations": [{
                    "method": "GET",
                    "path": "/match/dilemma/current",
                    "description": "CUSTOM API DESCRIPTION - should not be overwritten"
                }]
            },
            "traceability": {
                "wagon_ref": "plan/pace_dilemmas/_pace_dilemmas.yaml"
                # Missing feature_refs
            },
            "testing": {
                "directory": "contracts/match/dilemma/tests/"
                # Missing schema_tests array
            }
        }
    }
    with open(existing_contract, 'w') as f:
        json.dump(contract_data, f, indent=2)

    # Import validation function
    from atdd.coach.commands.interface import validate_and_update_contract_metadata

    # Execute validation and update
    result = validate_and_update_contract_metadata(
        contract_path=existing_contract,
        plan_dir=plan_dir,
        contracts_dir=contracts_dir
    )

    # Read updated contract
    with open(existing_contract) as f:
        updated_contract = json.load(f)

    metadata = updated_contract["x-artifact-metadata"]

    # Verify new consumer was added
    assert "wagon:resolve-dilemmas" in metadata["consumers"], "Should add new consumer"

    # Verify custom description was preserved
    assert updated_contract["description"] == "CUSTOM DESCRIPTION - should not be overwritten", \
        "Should preserve custom description"

    # Verify custom API description was preserved
    api_desc = metadata["api"]["operations"][0].get("description", "")
    assert "CUSTOM API DESCRIPTION" in api_desc, "Should preserve custom API description"

    # Verify missing feature_refs was added
    assert "feature_refs" in metadata["traceability"], "Should add missing feature_refs"

    # Verify missing schema_tests was added
    assert "schema_tests" in metadata["testing"], "Should add missing schema_tests array"
    assert len(metadata["testing"]["schema_tests"]) > 0, "Should populate schema_tests"

    # Verify result report
    assert "consumers" in result["updates"], "Should report consumers update"
    assert "traceability.feature_refs" in result["updates"], "Should report feature_refs added"
    assert "testing.schema_tests" in result["updates"], "Should report schema_tests added"
    assert result["preserved_customizations"] > 0, "Should count preserved customizations"


@pytest.mark.platform
def test_create_placeholder_contract_tests(tmp_path):
    """
    SPEC-COACH-UTILS-0296: Create placeholder test files for scaffolded contracts

    Given: Contract has been scaffolded with x-artifact-metadata.testing section
           Testing directory path specified in x-artifact-metadata.testing.directory
           Test file names specified in x-artifact-metadata.testing.schema_tests array
           Test directory may or may not exist
           Test files may or may not exist
    When: Creating placeholder test files for new contracts
    Then: Create testing directory if it does not exist
          For each test file in schema_tests array check if file exists
          If test file does not exist create placeholder test JSON file
          Placeholder contains minimal valid test structure with contract reference
          Placeholder includes TODO comment indicating it needs implementation
          Existing test files are not overwritten or modified
          Report which test files were created vs already existed
    """
    # Setup test directories
    contracts_dir = tmp_path / "contracts"
    contracts_dir.mkdir()

    # Create contract with testing metadata
    mechanic_dir = contracts_dir / "mechanic" / "timebank"
    mechanic_dir.mkdir(parents=True)
    contract_path = mechanic_dir / "exhausted.schema.json"

    contract_data = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "$id": "mechanic:timebank.exhausted",
        "version": "1.0.0",
        "title": "Timebank Exhausted",
        "type": "object",
        "x-artifact-metadata": {
            "domain": "timebank",
            "resource": "timebank.exhausted",
            "testing": {
                "directory": "contracts/mechanic/timebank/tests/",
                "schema_tests": [
                    "exhausted_schema_test.json",
                    "exhausted_validation_test.json"
                ]
            }
        }
    }
    with open(contract_path, 'w') as f:
        json.dump(contract_data, f, indent=2)

    # Create ONE existing test file to verify it's not overwritten
    tests_dir = mechanic_dir / "tests"
    tests_dir.mkdir()
    existing_test = tests_dir / "exhausted_schema_test.json"
    existing_test_data = {
        "description": "EXISTING TEST - should not be overwritten",
        "contract": "mechanic:timebank.exhausted"
    }
    with open(existing_test, 'w') as f:
        json.dump(existing_test_data, f, indent=2)

    # Import function
    from atdd.coach.commands.interface import create_placeholder_test_files

    # Execute placeholder generation
    result = create_placeholder_test_files(
        contract_path=contract_path,
        contracts_dir=contracts_dir
    )

    # Verify test directory exists
    assert tests_dir.exists(), "Test directory should exist"

    # Verify existing test was NOT modified
    with open(existing_test) as f:
        preserved_test = json.load(f)
    assert preserved_test["description"] == "EXISTING TEST - should not be overwritten", \
        "Should not overwrite existing test"

    # Verify new test was created
    new_test = tests_dir / "exhausted_validation_test.json"
    assert new_test.exists(), "Should create new placeholder test"

    # Verify placeholder structure
    with open(new_test) as f:
        placeholder = json.load(f)

    assert "TODO" in placeholder.get("description", ""), "Should include TODO comment"
    assert placeholder.get("contract") == "mechanic:timebank.exhausted", "Should reference contract"
    assert "test_cases" in placeholder, "Should have test_cases structure"

    # Verify result report
    assert result["created"] == 1, "Should report 1 file created"
    assert result["skipped"] == 1, "Should report 1 file skipped (existing)"
    assert "exhausted_validation_test.json" in result["created_files"], \
        "Should list created file"
    assert "exhausted_schema_test.json" in result["skipped_files"], \
        "Should list skipped file"
