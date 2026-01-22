"""
Platform tests: Wagon manifest schema validation.

Validates that all wagon manifests in plan/ conform to wagon.schema.json.
Tests are parametrized to run once per wagon manifest for surgical diagnostics.
"""
import pytest
import jsonschema
from pathlib import Path


@pytest.mark.platform
@pytest.mark.e2e
def test_wagon_manifest_matches_schema(wagon_schema, wagon_manifests):
    """
    SPEC-PLATFORM-WAGONS-0001: Wagon manifest validates against wagon.schema.json

    Given: A wagon manifest YAML file in plan/
    When: Validated against .claude/schemas/planner/wagon.schema.json
    Then: Validation passes with no schema errors
          All required fields are present
          URN patterns match expected format
    """
    errors = []

    for manifest_path, manifest in wagon_manifests:
        try:
            jsonschema.validate(manifest, wagon_schema)
        except jsonschema.ValidationError as e:
            errors.append(
                f"Wagon manifest validation failed for {manifest_path}:\n"
                f"  Error: {e.message}\n"
                f"  Path: {' -> '.join(str(p) for p in e.path)}\n"
                f"  Schema path: {' -> '.join(str(p) for p in e.schema_path)}"
            )

    if errors:
        pytest.fail("\n\n".join(errors))


@pytest.mark.platform
def test_all_wagons_have_required_fields(wagon_manifests):
    """
    SPEC-PLATFORM-WAGONS-0002: All wagons have required top-level fields

    Given: All wagon manifests
    When: Checking required fields
    Then: Each wagon has: wagon, description, subject, context, action, goal, outcome
    """
    required_fields = ["wagon", "description", "subject", "context", "action", "goal", "outcome"]

    for path, manifest in wagon_manifests:
        missing_fields = [field for field in required_fields if field not in manifest]
        assert not missing_fields, \
            f"Wagon {path} missing required fields: {missing_fields}"


@pytest.mark.platform
def test_all_produce_items_have_contract_and_telemetry(wagon_manifests):
    """
    SPEC-PLATFORM-WAGONS-0003: All produce items have contract and telemetry fields

    Given: All wagon manifests with produce items
    When: Checking produce item structure
    Then: Each produce item has 'contract' and 'telemetry' fields
          Fields can be null but must be present
    """
    for path, manifest in wagon_manifests:
        for idx, produce_item in enumerate(manifest.get("produce", [])):
            assert "contract" in produce_item, \
                f"Wagon {path}: produce[{idx}] missing 'contract' field"
            assert "telemetry" in produce_item, \
                f"Wagon {path}: produce[{idx}] missing 'telemetry' field"


@pytest.mark.platform
def test_wagon_slugs_match_directory_names(wagon_manifests):
    """
    SPEC-PLATFORM-WAGONS-0004: Wagon slugs match their directory names

    Given: Wagon manifests in plan/{wagon_dirname}/ directories
    When: Comparing wagon field to directory name
    Then: Wagon slug (kebab-case) matches directory name (snake_case) after conversion
          Per SPEC-COACH-UTILS-0281: slug.replace('-','_')→dirname, dirname.replace('_','-')→slug
    """
    for path, manifest in wagon_manifests:
        wagon_slug = manifest.get("wagon", "")

        # Check if manifest is in a wagon-specific directory (not in plan/ root)
        if path.parent.name != "plan":
            directory_name = path.parent.name
            # Convert directory name (snake_case) to expected slug (kebab-case)
            expected_slug = directory_name.replace('_', '-')
            assert wagon_slug == expected_slug, \
                f"Wagon slug '{wagon_slug}' doesn't match expected slug '{expected_slug}' (from directory '{directory_name}') for {path}"


@pytest.mark.platform
def test_produce_artifact_names_follow_convention(wagon_manifests):
    """
    SPEC-PLATFORM-WAGONS-0005: Produce artifact names follow naming convention

    Given: Wagon produce items
    When: Checking artifact name format
    Then: Names follow pattern per artifact-naming.convention.yaml:
          - Hierarchy: domain:resource (colon for hierarchy)
          - Variants: domain:resource.variant (dot for facets)
          - Can have unlimited colons, typically 0-1 dots
    """
    import re

    # Pattern: domain(:category)*:aspect(.variant)? per artifact-naming.convention.yaml
    # Allows: commons:auth, commons:auth.claims, commons:ux:foundations:color.primary
    name_pattern = re.compile(r"^[a-z][a-z0-9\-]*:[a-z][a-z0-9\-:]*(\.[a-z][a-z0-9\-]+)?$")

    for path, manifest in wagon_manifests:
        for produce_item in manifest.get("produce", []):
            name = produce_item.get("name", "")
            if name:  # Skip empty names
                assert name_pattern.match(name), \
                    f"Wagon {path}: produce artifact name '{name}' doesn't match pattern per artifact-naming.convention.yaml"


@pytest.mark.platform
def test_contract_urns_match_pattern(wagon_manifests):
    """
    SPEC-PLATFORM-WAGONS-0006: Contract URNs follow naming convention

    Given: Wagon produce items with non-null contract URNs
    When: Validating URN format
    Then: Contract URNs match pattern per artifact-naming.convention.yaml:
          contract:{artifact_name} where artifact_name can have colons and dots
          Pattern: contract:domain(:category)*:aspect(.variant)?
    """
    import re

    # URN exactly matches artifact name with "contract:" prefix
    # Per artifact-naming.convention.yaml line 627-645
    contract_pattern = re.compile(r"^contract:[a-z][a-z0-9\-]*:[a-z][a-z0-9\-:]*(\.[a-z][a-z0-9\-]+)?$")

    for path, manifest in wagon_manifests:
        for produce_item in manifest.get("produce", []):
            contract = produce_item.get("contract")
            if contract and contract is not None:
                assert contract_pattern.match(contract), \
                    f"Wagon {path}: contract URN '{contract}' doesn't match pattern per artifact-naming.convention.yaml"


@pytest.mark.platform
def test_telemetry_urns_match_pattern(wagon_manifests):
    """
    SPEC-PLATFORM-WAGONS-0007: Telemetry URNs follow multi-level pattern

    Given: Wagon produce items with non-null telemetry URNs
    When: Validating URN format
    Then: Telemetry URNs match pattern telemetry:{path}:{aspect}
          Supports multi-level paths (e.g., telemetry:commons:ux:foundations)
          Uses colons (not dots) for hierarchy
    """
    import re

    # Pattern: telemetry: followed by 2+ colon-separated segments (kebab-case), optional dot for variant
    # Supports: telemetry:commons:ux:foundations, telemetry:match:dilemma.paired
    telemetry_pattern = re.compile(r"^telemetry:([a-z][a-z0-9\-]*:)+[a-z][a-z0-9\-]*(\.[a-z][a-z0-9\-]*)?$")

    for path, manifest in wagon_manifests:
        for produce_item in manifest.get("produce", []):
            telemetry = produce_item.get("telemetry")
            if telemetry and telemetry is not None:
                # Handle both string and list types
                telemetry_urns = telemetry if isinstance(telemetry, list) else [telemetry]
                for urn in telemetry_urns:
                    assert telemetry_pattern.match(urn), \
                        f"Wagon {path}: telemetry URN '{urn}' doesn't match pattern telemetry:{{path}}:{{aspect}}"
