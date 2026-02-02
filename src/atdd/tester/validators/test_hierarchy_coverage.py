"""
Tester hierarchy coverage validation.

ATDD Hierarchy Coverage Spec v0.1 - Section 3: Tester Coverage Rules

Validates:
- Acceptance <-> Tests (COVERAGE-TEST-3.1)
- Contract <-> Wagon (COVERAGE-TEST-3.2)
- Telemetry <-> Wagon (COVERAGE-TEST-3.3)
- Telemetry tracking manifest (COVERAGE-TEST-3.4)

Architecture:
- Uses shared fixtures from atdd.coach.validators.shared_fixtures
- Phased rollout via atdd.coach.utils.coverage_phase
- Exception handling via .atdd/config.yaml coverage.exceptions
"""

import pytest
import yaml
import json
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any, Optional

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.coverage_phase import (
    CoveragePhase,
    should_enforce,
    emit_coverage_warning
)


# Path constants
REPO_ROOT = find_repo_root()
PLAN_DIR = REPO_ROOT / "plan"
CONTRACTS_DIR = REPO_ROOT / "contracts"
TELEMETRY_DIR = REPO_ROOT / "telemetry"
PYTHON_DIR = REPO_ROOT / "python"
SUPABASE_DIR = REPO_ROOT / "supabase"
TEST_DIR = REPO_ROOT / "test"
E2E_DIR = REPO_ROOT / "e2e"


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def find_acceptance_references_in_tests() -> Set[str]:
    """
    Scan test files for acceptance URN references.

    Returns:
        Set of acceptance URNs found in test files
    """
    urn_pattern = re.compile(
        r'acc:[a-z][a-z0-9\-]*:[A-Z0-9]+-[A-Z0-9]+-\d{3}(?:-[a-z0-9-]+)?',
        re.IGNORECASE
    )

    found_urns: Set[str] = set()

    # Scan Python tests
    if PYTHON_DIR.exists():
        for test_file in PYTHON_DIR.rglob("test_*.py"):
            try:
                content = test_file.read_text(encoding="utf-8")
                matches = urn_pattern.findall(content)
                found_urns.update(matches)
            except Exception:
                pass

    # Scan TypeScript tests
    if SUPABASE_DIR.exists():
        for test_file in SUPABASE_DIR.rglob("*.test.ts"):
            try:
                content = test_file.read_text(encoding="utf-8")
                matches = urn_pattern.findall(content)
                found_urns.update(matches)
            except Exception:
                pass

    # Scan E2E tests
    if E2E_DIR.exists():
        for test_file in E2E_DIR.rglob("*.test.ts"):
            try:
                content = test_file.read_text(encoding="utf-8")
                matches = urn_pattern.findall(content)
                found_urns.update(matches)
            except Exception:
                pass

    # Scan Dart tests
    if TEST_DIR.exists():
        for test_file in TEST_DIR.rglob("*_test.dart"):
            try:
                content = test_file.read_text(encoding="utf-8")
                matches = urn_pattern.findall(content)
                found_urns.update(matches)
            except Exception:
                pass

    return found_urns


def get_contract_status(contract_path: Path) -> Optional[str]:
    """
    Extract status from contract schema x-artifact-metadata.

    Returns:
        Status string or None if not found
    """
    try:
        with open(contract_path) as f:
            data = json.load(f)
            metadata = data.get("x-artifact-metadata", {})
            return metadata.get("status")
    except Exception:
        return None


def get_telemetry_signal_status(signal_path: Path) -> Optional[str]:
    """
    Extract status from telemetry signal file.

    Returns:
        Status string or None if not found
    """
    try:
        with open(signal_path) as f:
            data = json.load(f)
            return data.get("status")
    except Exception:
        return None


# ============================================================================
# COVERAGE-TEST-3.1: Acceptance <-> Tests Coverage
# ============================================================================


@pytest.mark.tester
def test_all_acceptances_have_tests(all_acceptance_urns, coverage_exceptions):
    """
    COVERAGE-TEST-3.1: Every acceptance has at least one test.

    Given: All acceptance URNs from WMBT files
    When: Scanning test files for URN references
    Then: Every acceptance URN is referenced by at least one test
    """
    if not all_acceptance_urns:
        pytest.skip("No acceptance URNs found in plan/")

    allowed_acceptances = set(coverage_exceptions.get("acceptance_without_tests", []))

    # Find all acceptance references in tests
    test_references = find_acceptance_references_in_tests()

    # Normalize URNs for comparison (case-insensitive)
    test_references_lower = {urn.lower() for urn in test_references}

    violations = []

    for acceptance_urn in all_acceptance_urns:
        # Skip allowed exceptions
        if acceptance_urn in allowed_acceptances:
            continue

        # Check if acceptance is referenced (case-insensitive)
        if acceptance_urn.lower() not in test_references_lower:
            violations.append(acceptance_urn)

    if violations:
        if should_enforce(CoveragePhase.PLANNER_TESTER_ENFORCEMENT):
            pytest.fail(
                f"COVERAGE-TEST-3.1: Acceptances without tests ({len(violations)}):\n  " +
                "\n  ".join(violations[:20]) +
                (f"\n  ... and {len(violations) - 20} more" if len(violations) > 20 else "") +
                "\n\nAdd tests or coverage.exceptions.acceptance_without_tests"
            )
        else:
            for violation in violations[:10]:
                emit_coverage_warning(
                    "COVERAGE-TEST-3.1",
                    f"Acceptance without test: {violation}",
                    CoveragePhase.PLANNER_TESTER_ENFORCEMENT
                )


# ============================================================================
# COVERAGE-TEST-3.2: Contract <-> Wagon Coverage
# ============================================================================


@pytest.mark.tester
def test_all_contracts_referenced(wagon_manifests, coverage_exceptions):
    """
    COVERAGE-TEST-3.2a: Every contract schema referenced by wagon.

    Given: Contract JSON files in contracts/
    When: Checking wagon produce/consume references
    Then: Every contract is referenced by at least one wagon
    """
    if not CONTRACTS_DIR.exists():
        pytest.skip("contracts/ directory does not exist")

    allowed_contracts = set(coverage_exceptions.get("contracts_unreferenced", []))

    # Build set of all contract references from wagons
    wagon_contract_refs: Set[str] = set()

    for path, manifest in wagon_manifests:
        for produce_item in manifest.get("produce", []):
            contract = produce_item.get("contract")
            if contract:
                wagon_contract_refs.add(contract)

        for consume_item in manifest.get("consume", []):
            contract = consume_item.get("contract")
            if contract:
                wagon_contract_refs.add(contract)

    # Find all contract files
    violations = []

    for contract_file in CONTRACTS_DIR.rglob("*.json"):
        # Skip non-schema files
        if contract_file.name.startswith("_"):
            continue

        # Check status
        status = get_contract_status(contract_file)
        if status in ("draft", "external", "deprecated"):
            continue

        # Build contract URN from path
        relative_path = contract_file.relative_to(CONTRACTS_DIR)
        # contracts/domain/resource.json -> contract:domain:resource
        parts = list(relative_path.parts)
        if len(parts) >= 2:
            domain = parts[0]
            resource = parts[-1].replace(".json", "")
            # Handle nested paths (category)
            if len(parts) > 2:
                category = "/".join(parts[1:-1])
                resource = f"{category}/{resource}"

            contract_urn = f"contract:{domain}:{resource}"

            # Skip allowed exceptions
            if contract_urn in allowed_contracts:
                continue

            # Check if referenced
            is_referenced = any(
                contract_urn in ref or ref.endswith(f":{resource}")
                for ref in wagon_contract_refs
            )

            if not is_referenced:
                violations.append(
                    f"{contract_file.relative_to(REPO_ROOT)}: not referenced by any wagon"
                )

    if violations:
        if should_enforce(CoveragePhase.PLANNER_TESTER_ENFORCEMENT):
            pytest.fail(
                f"COVERAGE-TEST-3.2a: Contracts not referenced:\n  " +
                "\n  ".join(violations[:20]) +
                (f"\n  ... and {len(violations) - 20} more" if len(violations) > 20 else "") +
                "\n\nAdd to wagon produce/consume or coverage.exceptions.contracts_unreferenced"
            )
        else:
            for violation in violations[:10]:
                emit_coverage_warning(
                    "COVERAGE-TEST-3.2a",
                    violation,
                    CoveragePhase.PLANNER_TESTER_ENFORCEMENT
                )


@pytest.mark.tester
def test_all_contract_refs_exist(wagon_manifests):
    """
    COVERAGE-TEST-3.2b: Every wagon contract ref has schema file.

    Given: Wagon produce/consume with contract fields
    When: Checking for corresponding files
    Then: Every contract reference has a schema file
    """
    if not CONTRACTS_DIR.exists():
        pytest.skip("contracts/ directory does not exist")

    violations = []

    for path, manifest in wagon_manifests:
        wagon_slug = manifest.get("wagon", path.parent.name)

        all_contract_refs = []

        for produce_item in manifest.get("produce", []):
            contract = produce_item.get("contract")
            if contract:
                all_contract_refs.append((contract, "produce"))

        for consume_item in manifest.get("consume", []):
            contract = consume_item.get("contract")
            if contract:
                all_contract_refs.append((contract, "consume"))

        for contract_ref, ref_type in all_contract_refs:
            # Parse contract URN: contract:domain:resource
            if contract_ref.startswith("contract:"):
                parts = contract_ref.split(":")
                if len(parts) >= 3:
                    domain = parts[1]
                    resource = ":".join(parts[2:])  # Handle nested resources

                    # Try to find the contract file
                    contract_path = CONTRACTS_DIR / domain / f"{resource}.json"
                    contract_path_nested = CONTRACTS_DIR / domain / resource / "index.json"

                    if not contract_path.exists() and not contract_path_nested.exists():
                        violations.append(
                            f"{wagon_slug}: {ref_type} contract '{contract_ref}' - file not found"
                        )

    if violations:
        if should_enforce(CoveragePhase.PLANNER_TESTER_ENFORCEMENT):
            pytest.fail(
                f"COVERAGE-TEST-3.2b: Contract references without files:\n  " +
                "\n  ".join(violations)
            )
        else:
            for violation in violations:
                emit_coverage_warning(
                    "COVERAGE-TEST-3.2b",
                    violation,
                    CoveragePhase.PLANNER_TESTER_ENFORCEMENT
                )


# ============================================================================
# COVERAGE-TEST-3.3: Telemetry <-> Wagon Coverage
# ============================================================================


@pytest.mark.tester
def test_all_telemetry_referenced(wagon_manifests, coverage_exceptions):
    """
    COVERAGE-TEST-3.3a: Every telemetry signal referenced by wagon.

    Given: Telemetry signal files in telemetry/
    When: Checking wagon produce references
    Then: Every telemetry signal is referenced by at least one wagon
    """
    if not TELEMETRY_DIR.exists():
        pytest.skip("telemetry/ directory does not exist")

    allowed_telemetry = set(coverage_exceptions.get("telemetry_unreferenced", []))

    # Build set of all telemetry references from wagons
    wagon_telemetry_refs: Set[str] = set()

    for path, manifest in wagon_manifests:
        for produce_item in manifest.get("produce", []):
            telemetry = produce_item.get("telemetry")
            if telemetry:
                if isinstance(telemetry, list):
                    wagon_telemetry_refs.update(telemetry)
                else:
                    wagon_telemetry_refs.add(telemetry)

    # Find all telemetry directories (each dir represents a telemetry URN)
    violations = []

    for domain_dir in TELEMETRY_DIR.iterdir():
        if not domain_dir.is_dir() or domain_dir.name.startswith("_"):
            continue

        for resource_dir in domain_dir.iterdir():
            if not resource_dir.is_dir():
                continue

            # Check for signal files
            signal_files = list(resource_dir.glob("*.json"))
            if not signal_files:
                continue

            # Check status of first signal
            status = get_telemetry_signal_status(signal_files[0])
            if status in ("draft", "external", "deprecated"):
                continue

            # Build telemetry URN
            telemetry_urn = f"telemetry:{domain_dir.name}:{resource_dir.name}"

            # Skip allowed exceptions
            if telemetry_urn in allowed_telemetry:
                continue

            # Check if referenced
            is_referenced = any(
                telemetry_urn in ref or ref.endswith(f":{resource_dir.name}")
                for ref in wagon_telemetry_refs
            )

            if not is_referenced:
                violations.append(
                    f"{resource_dir.relative_to(REPO_ROOT)}: not referenced by any wagon"
                )

    if violations:
        if should_enforce(CoveragePhase.PLANNER_TESTER_ENFORCEMENT):
            pytest.fail(
                f"COVERAGE-TEST-3.3a: Telemetry not referenced:\n  " +
                "\n  ".join(violations[:20]) +
                (f"\n  ... and {len(violations) - 20} more" if len(violations) > 20 else "") +
                "\n\nAdd to wagon produce or coverage.exceptions.telemetry_unreferenced"
            )
        else:
            for violation in violations[:10]:
                emit_coverage_warning(
                    "COVERAGE-TEST-3.3a",
                    violation,
                    CoveragePhase.PLANNER_TESTER_ENFORCEMENT
                )


@pytest.mark.tester
def test_all_telemetry_refs_exist(wagon_manifests):
    """
    COVERAGE-TEST-3.3b: Every wagon telemetry ref has signal files.

    Given: Wagon produce with telemetry fields
    When: Checking for corresponding directories
    Then: Every telemetry reference has signal files
    """
    if not TELEMETRY_DIR.exists():
        pytest.skip("telemetry/ directory does not exist")

    violations = []

    for path, manifest in wagon_manifests:
        wagon_slug = manifest.get("wagon", path.parent.name)

        for produce_item in manifest.get("produce", []):
            telemetry = produce_item.get("telemetry")
            if not telemetry:
                continue

            telemetry_refs = telemetry if isinstance(telemetry, list) else [telemetry]

            for telemetry_ref in telemetry_refs:
                # Parse telemetry URN: telemetry:domain:resource[.category]
                if telemetry_ref.startswith("telemetry:"):
                    parts = telemetry_ref.split(":")
                    if len(parts) >= 3:
                        domain = parts[1]
                        resource = parts[2]

                        # Handle category suffix (resource.category)
                        if "." in resource:
                            resource_parts = resource.split(".")
                            resource = resource_parts[0]
                            category = "/".join(resource_parts[1:])
                            telemetry_path = TELEMETRY_DIR / domain / resource / category
                        else:
                            telemetry_path = TELEMETRY_DIR / domain / resource

                        # Check if directory exists with signal files
                        if not telemetry_path.exists():
                            violations.append(
                                f"{wagon_slug}: telemetry '{telemetry_ref}' - directory not found"
                            )
                        elif not list(telemetry_path.glob("*.json")):
                            violations.append(
                                f"{wagon_slug}: telemetry '{telemetry_ref}' - no signal files"
                            )

    if violations:
        if should_enforce(CoveragePhase.PLANNER_TESTER_ENFORCEMENT):
            pytest.fail(
                f"COVERAGE-TEST-3.3b: Telemetry references without files:\n  " +
                "\n  ".join(violations)
            )
        else:
            for violation in violations:
                emit_coverage_warning(
                    "COVERAGE-TEST-3.3b",
                    violation,
                    CoveragePhase.PLANNER_TESTER_ENFORCEMENT
                )


# ============================================================================
# COVERAGE-TEST-3.4: Telemetry Tracking Manifest
# ============================================================================


@pytest.mark.tester
def test_telemetry_manifest_complete():
    """
    COVERAGE-TEST-3.4: Tracking manifest signals all exist as files.

    Given: telemetry/_tracking_manifest.yaml if present
    When: Checking listed signals
    Then: All signals in manifest have corresponding files
    """
    manifest_path = TELEMETRY_DIR / "_tracking_manifest.yaml"

    if not manifest_path.exists():
        pytest.skip("No telemetry tracking manifest found")

    try:
        with open(manifest_path) as f:
            manifest_data = yaml.safe_load(f)
    except Exception as e:
        pytest.fail(f"Failed to load tracking manifest: {e}")

    violations = []

    signals = manifest_data.get("signals", [])
    for signal_entry in signals:
        if isinstance(signal_entry, dict):
            signal_path = signal_entry.get("path")
            signal_urn = signal_entry.get("urn")
        else:
            signal_path = signal_entry
            signal_urn = signal_entry

        if signal_path:
            full_path = TELEMETRY_DIR / signal_path
            if not full_path.exists():
                violations.append(f"{signal_urn or signal_path}: file not found")

    if violations:
        if should_enforce(CoveragePhase.PLANNER_TESTER_ENFORCEMENT):
            pytest.fail(
                f"COVERAGE-TEST-3.4: Tracking manifest signals missing:\n  " +
                "\n  ".join(violations)
            )
        else:
            for violation in violations:
                emit_coverage_warning(
                    "COVERAGE-TEST-3.4",
                    violation,
                    CoveragePhase.PLANNER_TESTER_ENFORCEMENT
                )


# ============================================================================
# COVERAGE SUMMARY
# ============================================================================


@pytest.mark.tester
def test_tester_coverage_summary(
    all_acceptance_urns,
    wagon_manifests,
    coverage_thresholds
):
    """
    COVERAGE-TEST-SUMMARY: Report tester coverage statistics.

    This test always passes but reports coverage metrics for visibility.
    """
    # Count acceptance coverage
    test_references = find_acceptance_references_in_tests()
    test_references_lower = {urn.lower() for urn in test_references}

    covered_acceptances = sum(
        1 for urn in all_acceptance_urns
        if urn.lower() in test_references_lower
    )
    total_acceptances = len(all_acceptance_urns)

    # Calculate coverage percentage
    coverage_pct = (covered_acceptances / total_acceptances * 100) if total_acceptances > 0 else 0
    threshold = coverage_thresholds.get("min_acceptance_coverage", 80)

    # Count contracts
    total_contracts = 0
    if CONTRACTS_DIR.exists():
        total_contracts = len(list(CONTRACTS_DIR.rglob("*.json")))

    # Count telemetry
    total_telemetry = 0
    if TELEMETRY_DIR.exists():
        for domain_dir in TELEMETRY_DIR.iterdir():
            if domain_dir.is_dir() and not domain_dir.name.startswith("_"):
                total_telemetry += sum(1 for _ in domain_dir.iterdir() if _.is_dir())

    # Report summary
    summary = (
        f"\n\nTester Coverage Summary:\n"
        f"  Acceptances covered: {covered_acceptances}/{total_acceptances} ({coverage_pct:.1f}%)\n"
        f"  Coverage threshold: {threshold}%\n"
        f"  Total contracts: {total_contracts}\n"
        f"  Total telemetry domains: {total_telemetry}"
    )

    # This test always passes - it's informational
    assert True, summary
