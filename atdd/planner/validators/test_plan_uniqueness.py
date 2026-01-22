"""
Platform tests: Uniqueness constraints.

Validates that entities have unique identifiers across the repository.
Tests ensure no duplicate wagon slugs, train IDs, or WMBT IDs.
"""
import pytest
from collections import Counter
from typing import Dict, List, Any


@pytest.mark.platform
def test_wagon_slugs_are_unique(wagon_manifests):
    """
    SPEC-PLATFORM-UNIQUE-0001: Wagon slugs are unique across repository

    Given: All wagon manifests
    When: Checking wagon slug uniqueness
    Then: Each wagon slug appears exactly once
          No two wagons share the same slug
    """
    wagon_slugs = [manifest.get("wagon", "") for _, manifest in wagon_manifests]
    slug_counts = Counter(wagon_slugs)

    duplicates = {slug: count for slug, count in slug_counts.items() if count > 1}

    assert not duplicates, \
        f"Found duplicate wagon slugs:\n" + \
        "\n".join(f"  '{slug}': {count} occurrences" for slug, count in duplicates.items())


@pytest.mark.platform
def test_train_ids_are_unique(trains_registry):
    """
    SPEC-PLATFORM-UNIQUE-0002: Train IDs are unique across repository

    Given: All train definitions in plan/_trains.yaml
    When: Checking train_id uniqueness
    Then: Each train_id appears exactly once
    """
    train_ids = [train.get("train_id", "") for train in trains_registry.get("trains", [])]
    train_id_counts = Counter(train_ids)

    duplicates = {tid: count for tid, count in train_id_counts.items() if count > 1}

    assert not duplicates, \
        f"Found duplicate train IDs:\n" + \
        "\n".join(f"  '{tid}': {count} occurrences" for tid, count in duplicates.items())


@pytest.mark.platform
def test_produce_artifact_names_unique_per_wagon(wagon_manifests):
    """
    SPEC-PLATFORM-UNIQUE-0003: Produce artifact names unique within each wagon

    Given: Wagon produce items
    When: Checking artifact name uniqueness per wagon
    Then: Each wagon has unique produce artifact names
          No wagon produces the same artifact name twice
    """
    errors = []

    for path, manifest in wagon_manifests:
        wagon_slug = manifest.get("wagon", "")
        artifact_names = [item.get("name", "") for item in manifest.get("produce", [])]

        name_counts = Counter(artifact_names)
        duplicates = {name: count for name, count in name_counts.items() if count > 1}

        if duplicates:
            errors.append(
                f"Wagon '{wagon_slug}' at {path} has duplicate produce names:\n" +
                "\n".join(f"    '{name}': {count} occurrences" for name, count in duplicates.items())
            )

    if errors:
        pytest.fail("\n\n".join(errors))


@pytest.mark.platform
def test_wmbt_ids_unique_per_wagon(wagon_manifests):
    """
    SPEC-PLATFORM-UNIQUE-0004: WMBT IDs are unique within each wagon

    Given: Wagon WMBT definitions
    When: Checking WMBT ID uniqueness per wagon
    Then: Each wagon has unique WMBT IDs
          No wagon defines the same WMBT ID twice
    """
    errors = []

    for path, manifest in wagon_manifests:
        wagon_slug = manifest.get("wagon", "")
        wmbt_section = manifest.get("wmbt", {})

        # WMBT section can be dict or list - handle both formats
        if isinstance(wmbt_section, dict):
            wmbt_ids = list(wmbt_section.keys())
        elif isinstance(wmbt_section, list):
            wmbt_ids = [item.get("id", "") for item in wmbt_section]
        else:
            continue  # Skip if wmbt is not dict or list

        wmbt_id_counts = Counter(wmbt_ids)
        duplicates = {wid: count for wid, count in wmbt_id_counts.items() if count > 1}

        if duplicates:
            errors.append(
                f"Wagon '{wagon_slug}' at {path} has duplicate WMBT IDs:\n" +
                "\n".join(f"    '{wid}': {count} occurrences" for wid, count in duplicates.items())
            )

    if errors:
        pytest.fail("\n\n".join(errors))


@pytest.mark.platform
def test_feature_urns_unique_per_wagon(wagon_manifests):
    """
    SPEC-PLATFORM-UNIQUE-0005: Feature URNs are unique within each wagon

    Given: Wagon feature definitions (URN array format)
    When: Checking feature URN uniqueness per wagon
    Then: Each wagon has unique feature URNs
          No wagon defines the same feature URN twice
    """
    errors = []

    for path, manifest in wagon_manifests:
        wagon_slug = manifest.get("wagon", "")
        features = manifest.get("features", [])

        # Features can be array of URN objects or legacy dict - handle array format
        if isinstance(features, list):
            feature_urns = [item.get("urn", "") for item in features if isinstance(item, dict)]

            urn_counts = Counter(feature_urns)
            duplicates = {urn: count for urn, count in urn_counts.items() if count > 1}

            if duplicates:
                errors.append(
                    f"Wagon '{wagon_slug}' at {path} has duplicate feature URNs:\n" +
                    "\n".join(f"    '{urn}': {count} occurrences" for urn, count in duplicates.items())
                )

    if errors:
        pytest.fail("\n\n".join(errors))


@pytest.mark.platform
def test_contract_urns_unique_globally(wagon_manifests):
    """
    SPEC-PLATFORM-UNIQUE-0006: Contract URNs are unique globally

    Given: All contract URNs from wagon produce items
    When: Checking global uniqueness
    Then: Each contract URN is produced by exactly one wagon
          No two wagons produce the same contract URN
    """
    contract_to_wagons: Dict[str, List[str]] = {}

    for path, manifest in wagon_manifests:
        wagon_slug = manifest.get("wagon", "")

        for produce_item in manifest.get("produce", []):
            contract = produce_item.get("contract")
            if contract and contract is not None:
                contract_to_wagons.setdefault(contract, []).append(wagon_slug)

    # Find contracts produced by multiple wagons
    duplicates = {
        contract: wagons
        for contract, wagons in contract_to_wagons.items()
        if len(wagons) > 1
    }

    if duplicates:
        pytest.fail(
            f"Found contract URNs produced by multiple wagons:\n" +
            "\n".join(
                f"  '{contract}': {wagons}"
                for contract, wagons in duplicates.items()
            )
        )


@pytest.mark.platform
def test_telemetry_urns_unique_globally(wagon_manifests):
    """
    SPEC-PLATFORM-UNIQUE-0007: Telemetry URNs are unique globally

    Given: All telemetry URNs from wagon produce items
    When: Checking global uniqueness
    Then: Each telemetry URN is produced by exactly one wagon
          No two wagons produce the same telemetry URN
    """
    telemetry_to_wagons: Dict[str, List[str]] = {}

    for path, manifest in wagon_manifests:
        wagon_slug = manifest.get("wagon", "")

        for produce_item in manifest.get("produce", []):
            telemetry = produce_item.get("telemetry")
            if telemetry and telemetry is not None:
                # Handle both string and list types
                telemetry_urns = telemetry if isinstance(telemetry, list) else [telemetry]
                for urn in telemetry_urns:
                    telemetry_to_wagons.setdefault(urn, []).append(wagon_slug)

    # Find telemetry URNs produced by multiple wagons
    duplicates = {
        telemetry: wagons
        for telemetry, wagons in telemetry_to_wagons.items()
        if len(wagons) > 1
    }

    if duplicates:
        pytest.fail(
            f"Found telemetry URNs produced by multiple wagons:\n" +
            "\n".join(
                f"  '{telemetry}': {wagons}"
                for telemetry, wagons in duplicates.items()
            )
        )
