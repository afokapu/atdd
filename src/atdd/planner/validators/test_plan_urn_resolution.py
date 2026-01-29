"""
Platform tests: URN resolution to filesystem.

Validates that contract and telemetry URNs resolve to actual directories/files.
Tests ensure URN to filesystem mapping follows conventions.
"""
import pytest
from pathlib import Path
from typing import Tuple

# Path constants
REPO_ROOT = Path(__file__).resolve().parents[4]
CONTRACTS_DIR = REPO_ROOT / "contracts"
TELEMETRY_DIR = REPO_ROOT / "telemetry"


def parse_urn(urn: str) -> Tuple:
    """Parse URN into components.

    Returns tuple of (type, *path_parts) where:
    - type: contract or telemetry
    - path_parts: remaining segments (2+ for multi-level paths)
    - Both : and . create directory levels per artifact-naming convention

    Examples:
    - contract:ux:foundations → ('contract', 'ux', 'foundations')
    - telemetry:commons:ux:foundations → ('telemetry', 'commons', 'ux', 'foundations')
    - telemetry:match:dilemma.paired → ('telemetry', 'match', 'dilemma', 'paired')
    """
    import re
    parts = urn.split(":", 1)  # Split into [type, rest]
    if len(parts) < 2:
        raise ValueError(f"Invalid URN format: {urn} (must have URN type)")

    urn_type = parts[0]
    rest = parts[1]

    # Split rest by both : and . per artifact-naming convention
    segments = re.split(r'[:\.]', rest)

    if len(segments) < 2:
        raise ValueError(f"Invalid URN format: {urn} (must have at least 2 path segments)")

    return tuple([urn_type] + segments)


@pytest.mark.platform
@pytest.mark.e2e
def test_contract_urn_resolves_to_directory(contract_urns):
    """
    SPEC-PLATFORM-URN-0001: Contract URNs resolve to filesystem directories

    Given: A contract URN from wagon produce (e.g., contract:ux:foundations)
    When: Mapping URN to filesystem path
    Then: contracts/{domain}/{resource}/ directory exists
          OR contracts/{domain}/ exists (for domain-level contracts)
    """
    errors = []

    for contract_urn in contract_urns:
        parts = parse_urn(contract_urn)
        urn_type = parts[0]
        path_parts = parts[1:]  # All parts after 'contract:'

        # Expected path: contracts/{path_parts joined}/
        # For contract:commons:player:identity -> contracts/commons/player/identity/
        # For contract:ux:foundations -> contracts/ux/foundations/
        expected_path = CONTRACTS_DIR / Path(*path_parts)

        # Also check for domain-level contracts: contracts/{domain}/
        domain_path = CONTRACTS_DIR / path_parts[0] if len(path_parts) >= 1 else None

        if not (expected_path.exists() or (domain_path and domain_path.exists())):
            errors.append(
                f"Contract URN {contract_urn} does not resolve to filesystem:\n"
                f"  Expected: {expected_path} OR {domain_path}\n"
                f"  Neither path exists"
            )

    if errors:
        pytest.fail("\n\n".join(errors))


@pytest.mark.platform
@pytest.mark.e2e
def test_telemetry_urn_resolves_to_directory(telemetry_urns):
    """
    SPEC-PLATFORM-URN-0002: Telemetry URNs resolve to filesystem directories

    Given: A telemetry URN from wagon produce
    When: Mapping URN to filesystem path
    Then: telemetry/{path}/ directory exists (multi-level paths supported)

    Examples:
    - telemetry:ux:foundations → telemetry/ux/foundations/
    - telemetry:commons:ux:foundations → telemetry/commons/ux/foundations/
    """
    errors = []

    for telemetry_urn in telemetry_urns:
        parts = parse_urn(telemetry_urn)
        urn_type = parts[0]
        path_parts = parts[1:]  # All parts after 'telemetry:'

        # Expected path: telemetry/{path}/{to}/{aspect}/
        expected_path = TELEMETRY_DIR / Path(*path_parts)

        if not expected_path.exists():
            errors.append(
                f"Telemetry URN {telemetry_urn} does not resolve to filesystem:\n"
                f"  Expected: {expected_path}\n"
                f"  Path does not exist"
            )

    if errors:
        pytest.fail("\n\n".join(errors))


@pytest.mark.platform
@pytest.mark.e2e
def test_telemetry_directory_contains_signal_files(telemetry_urns):
    """
    SPEC-PLATFORM-URN-0003: Telemetry directories contain signal JSON files

    Given: A telemetry URN that resolves to a directory
    When: Checking directory contents
    Then: Directory contains *.json files (signal definitions)
          Signal files follow pattern: {aspect}.{signal-type}.{plane}[.{measure}].json
    """
    errors = []

    for telemetry_urn in telemetry_urns:
        parts = parse_urn(telemetry_urn)
        path_parts = parts[1:]  # All parts after 'telemetry:'
        telemetry_path = TELEMETRY_DIR / Path(*path_parts)

        if not telemetry_path.exists():
            continue  # Tested in URN-0002

        # Find all JSON files in directory
        json_files = list(telemetry_path.glob("*.json"))

        if not json_files:
            errors.append(
                f"Telemetry directory {telemetry_path} exists but contains no *.json signal files"
            )

    if errors:
        pytest.fail("\n\n".join(errors))


@pytest.mark.platform
def test_all_contract_urns_are_unique(contract_urns):
    """
    SPEC-PLATFORM-URN-0004: Contract URNs are unique across wagons

    Given: All contract URNs from wagon produce items
    When: Checking for duplicates
    Then: Each contract URN appears only once
          No two wagons produce the same contract URN
    """
    from collections import Counter

    # contract_urns fixture already returns unique URNs (set to sorted)
    # This test validates the assumption
    urn_counts = Counter(contract_urns)
    duplicates = {urn: count for urn, count in urn_counts.items() if count > 1}

    assert not duplicates, \
        f"Found duplicate contract URNs (should be unique):\n" + \
        "\n".join(f"  {urn}: {count} occurrences" for urn, count in duplicates.items())


@pytest.mark.platform
def test_all_telemetry_urns_are_unique(telemetry_urns):
    """
    SPEC-PLATFORM-URN-0005: Telemetry URNs are unique across wagons

    Given: All telemetry URNs from wagon produce items
    When: Checking for duplicates
    Then: Each telemetry URN appears only once
          No two wagons produce the same telemetry URN
    """
    from collections import Counter

    # telemetry_urns fixture already returns unique URNs
    urn_counts = Counter(telemetry_urns)
    duplicates = {urn: count for urn, count in urn_counts.items() if count > 1}

    assert not duplicates, \
        f"Found duplicate telemetry URNs (should be unique):\n" + \
        "\n".join(f"  {urn}: {count} occurrences" for urn, count in duplicates.items())


@pytest.mark.platform
def test_contracts_directory_structure_matches_urns(contract_urns):
    """
    SPEC-PLATFORM-URN-0006: contracts/ structure aligns with URN domain/resource

    Given: Contract URNs and contracts/ directory
    When: Comparing URN domain/resource to directory structure
    Then: For each contract URN contract:domain:resource,
          contracts/{domain}/{resource}/ exists OR contracts/{domain}/ exists
    """
    if not CONTRACTS_DIR.exists():
        pytest.skip(f"contracts/ directory does not exist at {CONTRACTS_DIR}")
        return

    missing_paths = []

    for urn in contract_urns:
        parts = parse_urn(urn)
        urn_type = parts[0]
        path_parts = parts[1:]  # All parts after 'contract:'

        # Expected path: contracts/{path_parts joined}/
        resource_path = CONTRACTS_DIR / Path(*path_parts)
        domain_path = CONTRACTS_DIR / path_parts[0] if len(path_parts) >= 1 else None

        if not (resource_path.exists() or (domain_path and domain_path.exists())):
            missing_paths.append(
                f"  {urn} -> Expected: {resource_path} OR {domain_path}"
            )

    if missing_paths:
        pytest.fail(
            f"Found {len(missing_paths)} contract URNs without matching filesystem paths:\n" +
            "\n".join(missing_paths[:10]) +
            (f"\n  ... and {len(missing_paths) - 10} more" if len(missing_paths) > 10 else "")
        )


@pytest.mark.platform
def test_telemetry_directory_structure_matches_urns(telemetry_urns):
    """
    SPEC-PLATFORM-URN-0007: telemetry/ structure aligns with URN hierarchy

    Given: Telemetry URNs and telemetry/ directory
    When: Comparing URN path to directory structure
    Then: For each telemetry URN telemetry:{path}:{aspect},
          telemetry/{path}/{aspect}/ exists (supports multi-level paths)

    Examples:
    - telemetry:ux:foundations → telemetry/ux/foundations/
    - telemetry:commons:ux:foundations → telemetry/commons/ux/foundations/
    """
    if not TELEMETRY_DIR.exists():
        pytest.skip(f"telemetry/ directory does not exist at {TELEMETRY_DIR}")
        return

    missing_paths = []

    for urn in telemetry_urns:
        parts = parse_urn(urn)
        path_parts = parts[1:]  # All parts after 'telemetry:'
        expected_path = TELEMETRY_DIR / Path(*path_parts)

        if not expected_path.exists():
            missing_paths.append(
                f"  {urn} -> Expected: {expected_path}"
            )

    if missing_paths:
        pytest.fail(
            f"Found {len(missing_paths)} telemetry URNs without matching filesystem paths:\n" +
            "\n".join(missing_paths[:10]) +
            (f"\n  ... and {len(missing_paths) - 10} more" if len(missing_paths) > 10 else "")
        )
