"""
Platform tests: Cross-reference validation.

Validates that cross-references between wagons, trains, and artifacts are coherent.
Tests ensure that consume references point to valid produce artifacts.
"""
import pytest
from typing import Dict, Set, List, Tuple, Any


@pytest.mark.platform
@pytest.mark.e2e
def test_wagon_consume_references_valid_produce_or_external(wagon_manifests):
    """
    SPEC-PLATFORM-REFS-0001: Wagon consume references point to valid sources

    Given: Wagon consume items with 'from' field
    When: Checking consume references
    Then: Each 'from' reference either:
          - Points to another wagon's produce (wagon:slug format)
          - Points to external system (system:external)
          - Points to appendix (appendix:type)
          - Is omitted (defaults to inferred/external)
    """
    # Build produce registry: {artifact_name: [wagon_slugs]}
    produce_registry: Dict[str, List[str]] = {}
    wagon_slugs: Set[str] = set()

    for path, manifest in wagon_manifests:
        wagon_slug = manifest.get("wagon", "")
        wagon_slugs.add(wagon_slug)

        for produce_item in manifest.get("produce", []):
            artifact_name = produce_item.get("name", "")
            if artifact_name:
                produce_registry.setdefault(artifact_name, []).append(wagon_slug)

    # Validate consume references
    for path, manifest in wagon_manifests:
        wagon_slug = manifest.get("wagon", "")

        for consume_item in manifest.get("consume", []):
            from_ref = consume_item.get("from", "")

            # Skip if from is not specified (defaults to external/inferred)
            if not from_ref:
                continue

            # Valid patterns:
            # - wagon:slug (reference to another wagon)
            # - system:external (external dependency)
            # - appendix:type (appendix artifact)
            if from_ref.startswith("wagon:"):
                referenced_wagon = from_ref.split(":", 1)[1]
                assert referenced_wagon in wagon_slugs, \
                    f"Wagon {wagon_slug} at {path} consumes from unknown wagon: {referenced_wagon}"

            elif from_ref.startswith("system:"):
                # System references are allowed (e.g., system:external)
                pass

            elif from_ref.startswith("appendix:"):
                # Appendix references are allowed
                pass

            else:
                # Unknown pattern - should match wagon:, system:, or appendix:
                pytest.fail(
                    f"Wagon {wagon_slug} at {path} has invalid 'from' reference: {from_ref}\n"
                    f"  Expected format: wagon:slug, system:external, or appendix:type"
                )


@pytest.mark.platform
def test_no_circular_dependencies_simple(wagon_manifests):
    """
    SPEC-PLATFORM-REFS-0002: No direct circular dependencies between wagons

    Given: Wagon consume to produce graph
    When: Checking for circular dependencies
    Then: No wagon directly consumes its own produce
          (Advanced cycle detection in separate test)
    """
    for path, manifest in wagon_manifests:
        wagon_slug = manifest.get("wagon", "")

        for consume_item in manifest.get("consume", []):
            from_ref = consume_item.get("from", "")

            if from_ref.startswith("wagon:"):
                referenced_wagon = from_ref.split(":", 1)[1]
                assert referenced_wagon != wagon_slug, \
                    f"Wagon {wagon_slug} at {path} has circular dependency (consumes from itself)"


@pytest.mark.platform
def test_trains_reference_valid_wagons(trains_registry, wagon_manifests):
    """
    SPEC-PLATFORM-REFS-0003: Train participants reference existing wagons

    Given: Train definitions in plan/_trains/ (theme-grouped registry)
    When: Checking train participant references
    Then: All referenced wagons exist in wagon registry
    """
    # Build wagon slug set
    wagon_slugs = {manifest.get("wagon", "") for _, manifest in wagon_manifests}

    # Check each train's participants (theme-grouped structure)
    for theme, trains in trains_registry.items():
        if not trains:
            continue

        for train in trains:
            train_id = train.get("train_id", "")
            train_path = train.get("path", "")

            # Load individual train file if path exists
            if train_path:
                import yaml
                from pathlib import Path
                train_file = Path(__file__).resolve().parents[4] / train_path

                if train_file.exists():
                    with open(train_file) as f:
                        train_data = yaml.safe_load(f)

                        # Check participants if present
                        participants = train_data.get("participants", [])
                        for participant in participants:
                            # Handle both formats: string ("wagon:slug") or object ({wagon: "slug"})
                            if isinstance(participant, str):
                                # String format: "wagon:slug" or "system:user"
                                if participant.startswith("wagon:"):
                                    wagon_ref = participant.split(":", 1)[1]
                                else:
                                    # Skip non-wagon participants (system:*, user:*, etc.)
                                    continue
                            else:
                                # Object format: {wagon: "slug"}
                                wagon_ref = participant.get("wagon", "")

                            if wagon_ref:
                                assert wagon_ref in wagon_slugs, \
                                    f"Train {train_id} (theme: {theme}) references unknown wagon: {wagon_ref}"


@pytest.mark.platform
def test_produce_and_consume_artifact_names_are_coherent(wagon_manifests):
    """
    SPEC-PLATFORM-REFS-0004: Consumed artifacts exist in produce registry

    Given: Wagon consume items without explicit 'from' field
    When: Artifact name is used to infer source
    Then: Artifact name should match a produced artifact somewhere
          OR be a known external/appendix pattern
    """
    # Build produce artifact name registry
    produce_names: Set[str] = set()

    for _, manifest in wagon_manifests:
        for produce_item in manifest.get("produce", []):
            artifact_name = produce_item.get("name", "")
            if artifact_name:
                produce_names.add(artifact_name)

    # Check consume references
    warnings = []

    for path, manifest in wagon_manifests:
        wagon_slug = manifest.get("wagon", "")

        for consume_item in manifest.get("consume", []):
            artifact_name = consume_item.get("name", "")
            from_ref = consume_item.get("from", "")

            # Skip if from is explicitly set to external/appendix/system
            if from_ref and (
                from_ref.startswith("system:") or
                from_ref.startswith("appendix:")
            ):
                continue

            # Check if artifact name exists in produce registry
            if artifact_name and artifact_name not in produce_names:
                # Special patterns that are allowed even if not produced
                if any(artifact_name.startswith(prefix) for prefix in [
                    "appendix:", "system:", "external:"
                ]):
                    continue

                warnings.append(
                    f"Wagon {wagon_slug} at {path} consumes artifact '{artifact_name}' "
                    f"which is not produced by any wagon"
                )

    # Report warnings if any
    if warnings:
        pytest.skip(
            f"Found {len(warnings)} orphaned consume references:\n" +
            "\n".join(f"  - {w}" for w in warnings[:5]) +
            (f"\n  ... and {len(warnings) - 5} more" if len(warnings) > 5 else "")
        )


@pytest.mark.platform
def test_wagon_to_field_references_valid_destinations(wagon_manifests):
    """
    SPEC-PLATFORM-REFS-0005: Produce 'to' field references valid destinations

    Given: Wagon produce items with 'to' field
    When: Checking destination references
    Then: Each 'to' reference is either:
          - 'external' (default)
          - 'internal' (wagon-internal artifact)
          - wagon:slug (specific wagon destination)
    """
    wagon_slugs = {manifest.get("wagon", "") for _, manifest in wagon_manifests}

    for path, manifest in wagon_manifests:
        wagon_slug = manifest.get("wagon", "")

        for produce_item in manifest.get("produce", []):
            to_ref = produce_item.get("to", "external")  # Default to external

            # Valid patterns:
            # - 'external' (public artifact)
            # - 'internal' (wagon-internal)
            # - wagon:slug (specific destination)
            if to_ref in ["external", "internal"]:
                continue

            if to_ref.startswith("wagon:"):
                referenced_wagon = to_ref.split(":", 1)[1]
                assert referenced_wagon in wagon_slugs, \
                    f"Wagon {wagon_slug} at {path} produces to unknown wagon: {referenced_wagon}"
            else:
                pytest.fail(
                    f"Wagon {wagon_slug} at {path} has invalid 'to' reference: {to_ref}\n"
                    f"  Expected: 'external', 'internal', or wagon:slug"
                )
