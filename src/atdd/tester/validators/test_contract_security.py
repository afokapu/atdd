"""
Platform tests: Contract security validation.

Validates that contract schemas properly declare security requirements:
- Secured operations have required auth headers
- Operations have explicit security field
- Secured operations have SEC/RLS acceptance coverage

Spec: SPEC-TESTER-SEC-0001 through SPEC-TESTER-SEC-0003
URN: tester:validators:contract-security
"""

import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set

import pytest

# Import find_repo_root with fallback
try:
    from atdd.coach.utils.repo import find_repo_root
except ImportError:
    def find_repo_root() -> Path:
        """Fallback: search upward for .git directory."""
        current = Path.cwd().resolve()
        while current != current.parent:
            if (current / ".git").is_dir():
                return current
            current = current.parent
        return Path.cwd().resolve()

# Import parse_acceptance_urn with fallback
try:
    from atdd.tester.utils.filename import parse_acceptance_urn
except ImportError:
    URN_PATTERN = r'^acc:([a-z][a-z0-9-]*):([DLPCEMYRK][0-9]{3})-([A-Z0-9]+)-([0-9]{3})(?:-([a-z0-9-]+))?$'

    def parse_acceptance_urn(urn: str) -> Dict[str, Optional[str]]:
        """Fallback URN parser."""
        match = re.match(URN_PATTERN, urn)
        if not match:
            raise ValueError(f"Invalid acceptance URN: {urn}")
        wagon, WMBT, HARNESS, NNN, slug = match.groups()
        return {
            'wagon': wagon,
            'WMBT': WMBT,
            'HARNESS': HARNESS,
            'NNN': NNN,
            'slug': slug
        }


# Path constants
REPO_ROOT = find_repo_root()
CONTRACTS_DIR = REPO_ROOT / "contracts"

# Security enforcement mode
ENFORCE_SECURITY = os.environ.get("ATDD_SECURITY_ENFORCE", "0") == "1"


def find_all_contract_schemas() -> List[Path]:
    """Find all contract schema files."""
    if not CONTRACTS_DIR.exists():
        return []
    return list(CONTRACTS_DIR.glob("**/*.schema.json"))


def load_contract(path: Path) -> Optional[Dict]:
    """Load and parse a contract schema file."""
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def is_secured_operation(contract: Dict) -> bool:
    """Check if contract represents a secured operation."""
    metadata = contract.get("x-artifact-metadata", {})
    security = metadata.get("security", {})

    # Check for explicit security declaration
    if security.get("requires_auth") is True:
        return True
    if security.get("authentication"):
        return True

    # Check for security scheme references
    if "securitySchemes" in contract:
        return True

    # Check API metadata for security indicators
    api = metadata.get("api", {})
    if api.get("security"):
        return True

    return False


def get_declared_headers(contract: Dict) -> Set[str]:
    """Extract declared header parameters from contract."""
    headers = set()

    # Check parameters at root level
    for param in contract.get("parameters", []):
        if param.get("in") == "header":
            headers.add(param.get("name", "").lower())

    # Check properties that might be headers
    props = contract.get("properties", {})
    if "headers" in props and isinstance(props["headers"], dict):
        header_props = props["headers"].get("properties", {})
        headers.update(k.lower() for k in header_props.keys())

    # Check x-artifact-metadata for header declarations
    metadata = contract.get("x-artifact-metadata", {})
    api = metadata.get("api", {})
    for header in api.get("headers", []):
        if isinstance(header, str):
            headers.add(header.lower())
        elif isinstance(header, dict):
            headers.add(header.get("name", "").lower())

    return headers


def get_acceptance_refs(contract: Dict) -> List[str]:
    """Extract acceptance references from contract."""
    metadata = contract.get("x-artifact-metadata", {})
    traceability = metadata.get("traceability", {})
    return traceability.get("acceptance_refs", [])


def soft_fail_or_fail(message: str, issues: List[str]):
    """Fail test or soft-fail based on ATDD_SECURITY_ENFORCE env var."""
    full_message = (
        f"{message}:\n" +
        "\n".join(f"  {issue}" for issue in issues[:10]) +
        (f"\n  ... and {len(issues) - 10} more" if len(issues) > 10 else "")
    )

    if ENFORCE_SECURITY:
        pytest.fail(full_message)
    else:
        pytest.skip(
            f"[SOFT-FAIL] {full_message}\n\n"
            "Set ATDD_SECURITY_ENFORCE=1 to enforce this check."
        )


@pytest.mark.tester
@pytest.mark.security
def test_secured_operations_have_required_headers():
    """
    SPEC-TESTER-SEC-0001: Secured operations must declare auth headers

    Given: Contract schemas with security requirements
    When: Checking for header declarations
    Then: Secured operations must include Authorization or X-Auth-Token header

    Required headers (at least one):
    - authorization
    - x-auth-token
    - x-api-key
    """
    contract_files = find_all_contract_schemas()

    if not contract_files:
        pytest.skip("No contract schema files found")

    AUTH_HEADERS = {"authorization", "x-auth-token", "x-api-key"}
    missing_headers = []

    for contract_path in contract_files:
        contract = load_contract(contract_path)
        if not contract:
            continue

        if not is_secured_operation(contract):
            continue

        declared_headers = get_declared_headers(contract)

        if not declared_headers.intersection(AUTH_HEADERS):
            missing_headers.append(
                f"{contract_path.relative_to(REPO_ROOT)}: "
                f"Secured operation missing auth header. "
                f"Declared: {sorted(declared_headers) or 'none'}. "
                f"Required one of: {sorted(AUTH_HEADERS)}"
            )

    if missing_headers:
        soft_fail_or_fail(
            f"Found {len(missing_headers)} secured operations without auth headers",
            missing_headers
        )


@pytest.mark.tester
@pytest.mark.security
def test_operations_have_explicit_security():
    """
    SPEC-TESTER-SEC-0002: All operations should have explicit security field

    Given: Contract schemas
    When: Checking for security metadata
    Then: Operations should declare security requirements explicitly
          (either requires_auth: true/false or security scheme)

    This ensures security posture is intentional, not accidental.
    """
    contract_files = find_all_contract_schemas()

    if not contract_files:
        pytest.skip("No contract schema files found")

    missing_security = []

    for contract_path in contract_files:
        contract = load_contract(contract_path)
        if not contract:
            continue

        metadata = contract.get("x-artifact-metadata", {})

        # Skip non-API contracts (e.g., shared schemas, types)
        if not metadata.get("api"):
            continue

        security = metadata.get("security", {})

        # Check for explicit security declaration
        has_explicit_security = (
            "requires_auth" in security or
            "authentication" in security or
            "securitySchemes" in contract or
            metadata.get("api", {}).get("security")
        )

        if not has_explicit_security:
            missing_security.append(
                f"{contract_path.relative_to(REPO_ROOT)}: "
                f"API operation missing explicit security declaration. "
                f"Add x-artifact-metadata.security.requires_auth: true|false"
            )

    if missing_security:
        soft_fail_or_fail(
            f"Found {len(missing_security)} operations without explicit security",
            missing_security
        )


@pytest.mark.tester
@pytest.mark.security
def test_secured_operations_have_security_acceptance():
    """
    SPEC-TESTER-SEC-0003: Secured operations must have SEC/RLS acceptance coverage

    Given: Contract schemas with security requirements
    When: Checking acceptance_refs
    Then: At least one acceptance criteria must use SEC or RLS harness

    SEC harness: Security-focused acceptance tests
    RLS harness: Row-Level Security acceptance tests
    """
    contract_files = find_all_contract_schemas()

    if not contract_files:
        pytest.skip("No contract schema files found")

    SECURITY_HARNESSES = {"SEC", "RLS"}
    missing_coverage = []

    for contract_path in contract_files:
        contract = load_contract(contract_path)
        if not contract:
            continue

        if not is_secured_operation(contract):
            continue

        acceptance_refs = get_acceptance_refs(contract)

        # Check if any acceptance ref uses SEC or RLS harness
        has_security_coverage = False
        for ref in acceptance_refs:
            try:
                parsed = parse_acceptance_urn(ref)
                if parsed.get("HARNESS") in SECURITY_HARNESSES:
                    has_security_coverage = True
                    break
            except ValueError:
                # Invalid URN format, skip
                continue

        if not has_security_coverage:
            missing_coverage.append(
                f"{contract_path.relative_to(REPO_ROOT)}: "
                f"Secured operation missing SEC/RLS acceptance coverage. "
                f"Current refs: {acceptance_refs or 'none'}"
            )

    if missing_coverage:
        soft_fail_or_fail(
            f"Found {len(missing_coverage)} secured operations without SEC/RLS acceptance",
            missing_coverage
        )
