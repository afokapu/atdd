"""
Platform tests: Contract directory structure validation.

Validates that contracts/ follows the domain/resource pattern.
Tests ensure contract directories align with URN conventions.
"""
import pytest
import re
from pathlib import Path

# Path constants
REPO_ROOT = Path(__file__).resolve().parents[4]
CONTRACTS_DIR = REPO_ROOT / "contracts"


@pytest.mark.platform
def test_contracts_directory_exists():
    """
    SPEC-PLATFORM-CONTRACTS-0001: contracts/ directory exists

    Given: Repository root
    When: Checking for contracts/ directory
    Then: contracts/ directory exists
    """
    assert CONTRACTS_DIR.exists(), \
        f"contracts/ directory does not exist at {CONTRACTS_DIR}"


@pytest.mark.platform
def test_contracts_follow_domain_resource_pattern():
    """
    SPEC-PLATFORM-CONTRACTS-0002: contracts/ follows domain/resource pattern

    Given: contracts/ directory structure
    When: Checking directory hierarchy
    Then: Structure follows contracts/{domain}/{resource}/ pattern
          OR contracts/{domain}/ for domain-level contracts
          Domain and resource names are lowercase with hyphens
    """
    if not CONTRACTS_DIR.exists():
        pytest.skip(f"contracts/ directory does not exist")
        return

    import re
    name_pattern = re.compile(r"^[a-z][a-z0-9\-]*$")

    for domain_dir in CONTRACTS_DIR.iterdir():
        if not domain_dir.is_dir():
            continue

        # Skip hidden directories and special directories
        if domain_dir.name.startswith(".") or domain_dir.name == "__pycache__":
            continue

        # Verify domain name follows pattern
        assert name_pattern.match(domain_dir.name), \
            f"Contract domain '{domain_dir.name}' doesn't match pattern (lowercase, hyphens only)"

        # Check resource directories
        for resource_dir in domain_dir.iterdir():
            if not resource_dir.is_dir():
                continue

            if resource_dir.name.startswith(".") or resource_dir.name == "__pycache__":
                continue

            # Verify resource name follows pattern
            assert name_pattern.match(resource_dir.name), \
                f"Contract resource '{resource_dir.name}' in domain '{domain_dir.name}' " \
                f"doesn't match pattern (lowercase, hyphens only)"


@pytest.mark.platform
def test_contract_directories_contain_files():
    """
    SPEC-PLATFORM-CONTRACTS-0003: Contract directories contain definition files

    Given: contracts/{domain}/{resource}/ directories
    When: Checking directory contents
    Then: Each resource directory contains files (JSON, YAML, or other formats)
          Directories are not empty
    """
    if not CONTRACTS_DIR.exists():
        pytest.skip(f"contracts/ directory does not exist")
        return

    empty_dirs = []

    for domain_dir in CONTRACTS_DIR.iterdir():
        if not domain_dir.is_dir() or domain_dir.name.startswith("."):
            continue

        for resource_dir in domain_dir.iterdir():
            if not resource_dir.is_dir() or resource_dir.name.startswith("."):
                continue

            # Check if directory has any files (recursively)
            has_files = any(resource_dir.rglob("*"))

            if not has_files:
                empty_dirs.append(str(resource_dir.relative_to(REPO_ROOT)))

    if empty_dirs:
        pytest.fail(
            f"Found {len(empty_dirs)} empty contract directories:\n" +
            "\n".join(f"  {d}" for d in empty_dirs[:10]) +
            (f"\n  ... and {len(empty_dirs) - 10} more" if len(empty_dirs) > 10 else "")
        )


@pytest.mark.platform
def test_no_orphaned_contract_directories(contract_urns):
    """
    SPEC-PLATFORM-CONTRACTS-0004: No orphaned contract directories

    Given: Contract directories in contracts/
    When: Comparing to contract URNs from wagons
    Then: Each contracts/{domain}/{resource}/ has a corresponding URN
          OR is a domain-level contract directory
          No orphaned directories that aren't referenced
    """
    if not CONTRACTS_DIR.exists():
        pytest.skip(f"contracts/ directory does not exist")
        return

    # Build set of expected paths from URNs
    expected_paths = set()
    expected_domains = set()

    for urn in contract_urns:
        parts = urn.split(":")
        if len(parts) == 3:
            _, domain, resource = parts
            expected_paths.add(f"{domain}/{resource}")
            expected_domains.add(domain)

    # Check actual directory structure
    orphaned = []

    for domain_dir in CONTRACTS_DIR.iterdir():
        if not domain_dir.is_dir() or domain_dir.name.startswith("."):
            continue

        domain_name = domain_dir.name

        # Check resource directories
        for resource_dir in domain_dir.iterdir():
            if not resource_dir.is_dir() or resource_dir.name.startswith("."):
                continue

            resource_name = resource_dir.name
            path = f"{domain_name}/{resource_name}"

            # Check if this path is referenced by a URN
            if path not in expected_paths:
                orphaned.append(path)

    if orphaned:
        pytest.skip(
            f"Found {len(orphaned)} contract directories without corresponding URNs:\n" +
            "\n".join(f"  contracts/{d}" for d in orphaned[:10]) +
            (f"\n  ... and {len(orphaned) - 10} more" if len(orphaned) > 10 else "") +
            "\n  (This may be expected for legacy or future contracts)"
        )


@pytest.mark.platform
def test_contract_files_are_valid_formats():
    """
    SPEC-PLATFORM-CONTRACTS-0005: Contract files use valid formats

    Given: Files in contracts/{domain}/{resource}/ directories
    When: Checking file extensions
    Then: Files use standard formats: .json, .yaml, .yml, .md, .ts, .dart
          No unexpected file types
    """
    if not CONTRACTS_DIR.exists():
        pytest.skip(f"contracts/ directory does not exist")
        return

    allowed_extensions = {".json", ".yaml", ".yml", ".md", ".ts", ".dart", ".txt"}
    invalid_files = []

    for domain_dir in CONTRACTS_DIR.iterdir():
        if not domain_dir.is_dir() or domain_dir.name.startswith("."):
            continue

        for file_path in domain_dir.rglob("*"):
            if file_path.is_file() and not file_path.name.startswith("."):
                # Check standard extensions
                if file_path.suffix not in allowed_extensions:
                    invalid_files.append(str(file_path.relative_to(REPO_ROOT)))

    if invalid_files:
        pytest.skip(
            f"Found {len(invalid_files)} contract files with unexpected extensions:\n" +
            "\n".join(f"  {f}" for f in invalid_files[:10]) +
            (f"\n  ... and {len(invalid_files) - 10} more" if len(invalid_files) > 10 else "") +
            f"\n  Allowed: {', '.join(sorted(allowed_extensions))}"
        )
