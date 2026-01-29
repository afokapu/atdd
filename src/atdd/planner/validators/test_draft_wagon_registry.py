"""
Platform tests: Draft Wagon Registry Validation.

Validates draft wagons in plan/_wagons.yaml registry for coherence with:
- Existing wagon manifests (prevent duplicates)
- Contract/telemetry references (check artifact resolution)
- Traceability (cross-reference validation)
- Implementation status (manifest vs draft)

Tests help agents make better decisions when encountering references to non-existent wagons
by checking the registry first before assuming external services.
"""
import pytest
import yaml
from pathlib import Path
from atdd.coach.validators.shared_fixtures import PLAN_DIR


@pytest.fixture(scope="module")
def wagon_registry():
    """Load plan/_wagons.yaml registry."""
    registry_path = PLAN_DIR / "_wagons.yaml"
    if not registry_path.exists():
        pytest.skip(f"Wagon registry not found: {registry_path}")

    with open(registry_path) as f:
        data = yaml.safe_load(f)

    return data.get("wagons", [])


@pytest.fixture(scope="module")
def implemented_wagon_slugs(wagon_manifests):
    """Extract wagon slugs that have manifests (implemented)."""
    slugs = set()
    for manifest_path, manifest in wagon_manifests:
        slug = manifest.get("wagon", "")
        if slug:
            slugs.add(slug)
    return slugs


@pytest.fixture(scope="module")
def draft_wagons(wagon_registry, implemented_wagon_slugs):
    """Filter wagons from registry that are drafts (no manifest/path)."""
    drafts = []
    for wagon in wagon_registry:
        slug = wagon.get("wagon", "")
        # Draft wagons don't have 'manifest' or 'path' fields
        has_manifest = wagon.get("manifest") or wagon.get("path")
        is_implemented = slug in implemented_wagon_slugs

        if not has_manifest and not is_implemented:
            drafts.append(wagon)

    return drafts


@pytest.fixture(scope="module")
def all_registry_wagon_slugs(wagon_registry):
    """Get all wagon slugs from registry (both draft and implemented)."""
    return {wagon.get("wagon", "") for wagon in wagon_registry if wagon.get("wagon")}


@pytest.mark.platform
def test_draft_wagons_are_valid_yaml(draft_wagons):
    """
    SPEC-PLATFORM-REGISTRY-0001: Draft wagons have valid structure

    Given: Draft wagons in plan/_wagons.yaml
    When: Checking basic structure
    Then: Each draft has required fields: wagon, description, theme, subject
    """
    required_fields = ["wagon", "description", "theme", "subject", "context", "action", "goal", "outcome"]

    errors = []
    for draft in draft_wagons:
        wagon_slug = draft.get("wagon", "UNKNOWN")
        for field in required_fields:
            if field not in draft:
                errors.append(
                    f"Draft wagon '{wagon_slug}' missing required field: {field}"
                )

    if errors:
        pytest.fail("\n".join(errors))


@pytest.mark.platform
def test_draft_wagons_not_duplicated_in_manifests(draft_wagons, implemented_wagon_slugs):
    """
    SPEC-PLATFORM-REGISTRY-0002: Draft wagons don't have manifests

    Given: Draft wagons in registry
    When: Checking against implemented wagon manifests
    Then: Draft wagon slugs should NOT have manifest files
          (If they do, they're implemented, not draft)
    """
    errors = []
    for draft in draft_wagons:
        slug = draft.get("wagon", "")
        if slug in implemented_wagon_slugs:
            errors.append(
                f"Wagon '{slug}' is in registry as draft but has manifest file - "
                f"should add 'manifest' and 'path' fields to registry entry"
            )

    if errors:
        pytest.fail("\n\n".join(errors))


@pytest.mark.platform
def test_registry_produce_artifacts_follow_convention(wagon_registry):
    """
    SPEC-PLATFORM-REGISTRY-0003: Registry produce artifacts follow artifact-naming convention v2.1

    Given: All wagons in registry (draft + implemented)
    When: Checking produce artifact names
    Then: All artifacts follow pattern: {theme}(:{category})*:{aspect}(.{variant})?
          Supports unlimited hierarchical depth with colons (e.g., commons:ux:foundations)
          Supports optional variant with dot (e.g., match:dilemma.paired)
    """
    import re
    # Pattern per artifact-naming.convention.yaml v2.1:
    # {theme}(:{category})*:{aspect}(.{variant})?
    # - theme: required (1 segment)
    # - categories: optional (0+ segments with colons)
    # - aspect: required (1 segment)
    # - variant: optional (1 segment with dot)
    artifact_pattern = re.compile(r"^[a-z][a-z0-9-]+:[a-z][a-z0-9-]+(:[a-z][a-z0-9-]+)*(\.[a-z][a-z0-9-]+)?$")

    errors = []
    for wagon in wagon_registry:
        wagon_slug = wagon.get("wagon", "UNKNOWN")
        produce_items = wagon.get("produce", [])

        for idx, item in enumerate(produce_items):
            name = item.get("name", "")
            if not artifact_pattern.match(name):
                errors.append(
                    f"Wagon '{wagon_slug}' produce[{idx}] has invalid artifact name: '{name}'\n"
                    f"  Expected pattern: {{theme}}(:{{category}})*:{{aspect}}(.{{variant}})?\n"
                    f"  Examples: commons:ux:foundations, match:dilemma.paired"
                )

    if errors:
        pytest.fail("\n\n".join(errors))


@pytest.mark.platform
def test_registry_consume_references_valid_wagons(wagon_registry, all_registry_wagon_slugs):
    """
    SPEC-PLATFORM-REGISTRY-0004: Registry consume references are coherent

    Given: All wagons in registry
    When: Checking consume 'from' references
    Then: wagon:slug references resolve to wagons in registry OR
          References use valid patterns: system:*, appendix:*, internal
    """
    errors = []

    for wagon in wagon_registry:
        wagon_slug = wagon.get("wagon", "UNKNOWN")
        consume_items = wagon.get("consume", [])

        for idx, item in enumerate(consume_items):
            from_ref = item.get("from", "")
            if not from_ref:
                continue

            # Check pattern validity
            if from_ref.startswith("wagon:"):
                referenced_wagon = from_ref.split(":", 1)[1]
                if referenced_wagon not in all_registry_wagon_slugs:
                    errors.append(
                        f"Wagon '{wagon_slug}' consume[{idx}] references unknown wagon: '{referenced_wagon}'\n"
                        f"  Reference: {from_ref}\n"
                        f"  Artifact: {item.get('name', 'UNKNOWN')}\n"
                        f"  Hint: Check if wagon exists in registry or should be system:* reference"
                    )

            elif from_ref.startswith("system:"):
                # System references are valid
                pass

            elif from_ref.startswith("appendix:"):
                # Appendix references are valid
                pass

            elif from_ref == "internal":
                # Internal reference is valid
                pass

            else:
                errors.append(
                    f"Wagon '{wagon_slug}' consume[{idx}] has invalid 'from' pattern: '{from_ref}'\n"
                    f"  Expected: wagon:slug, system:service, appendix:type, or internal"
                )

    if errors:
        pytest.fail("\n\n".join(errors))


@pytest.mark.platform
def test_registry_produce_artifacts_have_consumers(wagon_registry):
    """
    SPEC-PLATFORM-REGISTRY-0005: Registry produce artifacts are consumed

    Given: All wagons in registry
    When: Checking produce artifacts against all consume references
    Then: Each produce artifact should be consumed by at least one wagon
          (Orphaned artifacts should be flagged as warnings)

    Note: This is a soft validation - some artifacts may be consumed externally
    """
    # Build produce artifact registry
    produced_artifacts = {}  # artifact_name -> wagon_slug
    for wagon in wagon_registry:
        wagon_slug = wagon.get("wagon", "")
        for item in wagon.get("produce", []):
            artifact_name = item.get("name", "")
            if artifact_name:
                if artifact_name not in produced_artifacts:
                    produced_artifacts[artifact_name] = []
                produced_artifacts[artifact_name].append(wagon_slug)

    # Build consume artifact set
    consumed_artifacts = set()
    for wagon in wagon_registry:
        for item in wagon.get("consume", []):
            artifact_name = item.get("name", "")
            if artifact_name:
                consumed_artifacts.add(artifact_name)

    # Find orphaned artifacts
    warnings = []
    for artifact_name, producers in produced_artifacts.items():
        if artifact_name not in consumed_artifacts:
            producers_str = ", ".join(producers)
            warnings.append(
                f"Artifact '{artifact_name}' produced by [{producers_str}] "
                f"but not consumed by any wagon (may be external/endpoint)"
            )

    # Report warnings (not failures) - informational only
    if warnings:
        print(f"\n\n⚠️  Orphaned Artifacts (may be intentional for external consumption):")
        for warning in warnings:
            print(f"  • {warning}")


@pytest.mark.platform
def test_draft_wagon_contract_coherence(draft_wagons):
    """
    SPEC-PLATFORM-REGISTRY-0006: Draft wagon contract references are coherent

    Given: Draft wagons in registry
    When: Checking contract/telemetry URN references
    Then: URNs follow expected pattern: contract:domain:resource
          Telemetry follows: telemetry:domain:resource

    Note: This doesn't validate filesystem resolution (draft wagons don't have contracts yet)
          Just validates URN format coherence
    """
    import re
    contract_pattern = re.compile(r"^contract:[a-z]+:[a-z][a-z0-9-]+(\.[a-z][a-z0-9-]+)?$")
    telemetry_pattern = re.compile(r"^telemetry:[a-z]+:[a-z][a-z0-9-]+(\.[a-z][a-z0-9-]+)?$")

    errors = []

    for draft in draft_wagons:
        wagon_slug = draft.get("wagon", "UNKNOWN")

        # Check produce items
        for idx, item in enumerate(draft.get("produce", [])):
            # Contract URN
            if "contract" in item and item["contract"]:
                contract_urn = item["contract"]
                if not contract_pattern.match(contract_urn):
                    errors.append(
                        f"Draft wagon '{wagon_slug}' produce[{idx}] has invalid contract URN: '{contract_urn}'\n"
                        f"  Expected pattern: contract:domain:resource[.category]"
                    )

            # Telemetry URN
            if "telemetry" in item and item["telemetry"]:
                telemetry_urn = item["telemetry"]
                if not telemetry_pattern.match(telemetry_urn):
                    errors.append(
                        f"Draft wagon '{wagon_slug}' produce[{idx}] has invalid telemetry URN: '{telemetry_urn}'\n"
                        f"  Expected pattern: telemetry:domain:resource[.category]"
                    )

    if errors:
        pytest.fail("\n\n".join(errors))


@pytest.mark.platform
def test_registry_wagon_slugs_are_unique(wagon_registry):
    """
    SPEC-PLATFORM-REGISTRY-0007: Wagon slugs in registry are unique

    Given: All wagons in registry
    When: Checking wagon slugs
    Then: Each slug appears only once
    """
    slug_counts = {}
    for wagon in wagon_registry:
        slug = wagon.get("wagon", "")
        if slug:
            slug_counts[slug] = slug_counts.get(slug, 0) + 1

    duplicates = {slug: count for slug, count in slug_counts.items() if count > 1}

    if duplicates:
        errors = []
        for slug, count in duplicates.items():
            errors.append(f"Wagon slug '{slug}' appears {count} times in registry")
        pytest.fail("\n".join(errors))


@pytest.mark.platform
def test_registry_has_all_implemented_wagons(wagon_registry, implemented_wagon_slugs):
    """
    SPEC-PLATFORM-REGISTRY-0008: All implemented wagons are in registry

    Given: Wagon manifests in plan/*/
    When: Checking against registry
    Then: All wagon manifest slugs should be in registry
          (Registry is the source of truth)
    """
    registry_slugs = {wagon.get("wagon", "") for wagon in wagon_registry}

    missing_from_registry = implemented_wagon_slugs - registry_slugs

    if missing_from_registry:
        errors = [
            f"Wagon '{slug}' has manifest but is NOT in registry plan/_wagons.yaml"
            for slug in sorted(missing_from_registry)
        ]
        pytest.fail(
            "Implemented wagons missing from registry:\n" +
            "\n".join(f"  • {e}" for e in errors)
        )


@pytest.mark.platform
def test_registry_implemented_wagons_have_path_and_manifest(wagon_registry, implemented_wagon_slugs):
    """
    SPEC-PLATFORM-REGISTRY-0009: Implemented wagons have manifest/path fields

    Given: Wagons in registry that have manifests
    When: Checking registry entries
    Then: Registry entry should have 'manifest' and 'path' fields
          These fields help distinguish implemented vs draft wagons
    """
    errors = []

    for wagon in wagon_registry:
        slug = wagon.get("wagon", "")
        if slug in implemented_wagon_slugs:
            if not wagon.get("manifest"):
                errors.append(
                    f"Implemented wagon '{slug}' missing 'manifest' field in registry\n"
                    f"  Expected: manifest: plan/{slug.replace('-', '_')}/_{slug.replace('-', '_')}.yaml"
                )
            if not wagon.get("path"):
                errors.append(
                    f"Implemented wagon '{slug}' missing 'path' field in registry\n"
                    f"  Expected: path: plan/{slug.replace('-', '_')}/"
                )

    if errors:
        pytest.fail("\n\n".join(errors))
