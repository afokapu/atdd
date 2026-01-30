"""
Platform tests: Contract security validation.

Validates that contract schemas properly declare security requirements:
- Secured operations have required auth headers
- Operations have explicit security field
- Secured operations have SEC/RLS acceptance coverage
- Error responses do not expose sensitive data

Spec: SPEC-TESTER-SEC-0001 through SPEC-TESTER-SEC-0004
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

# Scheme to required headers mapping
SCHEME_HEADERS = {
    "jwt": {"authorization"},
    "bearer": {"authorization"},
    "oauth2": {"authorization"},
    "http": {"authorization"},
}

# Sensitive field names that should not appear in error responses
SENSITIVE_FIELDS = {"password", "secret", "credential", "ssn", "api_key", "private_key", "token"}
# Fields that are allowed even if they contain "key" or similar
ALLOWED_IN_ERRORS = {"error_key", "key_id", "token_type"}


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


def get_secured_operations(contract: Dict) -> List[Dict]:
    """Extract operations that have security defined."""
    metadata = contract.get("x-artifact-metadata", {})
    api = metadata.get("api", {})
    operations = api.get("operations", [])

    secured = []
    for op in operations:
        if not isinstance(op, dict):
            continue
        security = op.get("security", [])
        if security:  # Non-empty security array means secured
            secured.append(op)
    return secured


def is_secured_operation(contract: Dict) -> bool:
    """Check if contract represents a secured operation."""
    # First check operations-based security (preferred method)
    secured_ops = get_secured_operations(contract)
    if secured_ops:
        return True

    # Fallback to legacy metadata checks
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

    # Check operations for header declarations
    for op in api.get("operations", []):
        if not isinstance(op, dict):
            continue
        for header in op.get("headers", []):
            if isinstance(header, str):
                headers.add(header.lower())
            elif isinstance(header, dict):
                headers.add(header.get("name", "").lower())

    return headers


def get_operation_headers(operation: Dict) -> Set[str]:
    """Extract declared headers from a single operation."""
    headers = set()
    for header in operation.get("headers", []):
        if isinstance(header, str):
            headers.add(header.lower())
        elif isinstance(header, dict):
            headers.add(header.get("name", "").lower())
    return headers


def get_required_headers_for_security(security_schemes: List[Dict]) -> Set[str]:
    """Determine required headers based on security schemes."""
    required = set()
    for scheme in security_schemes:
        if not isinstance(scheme, dict):
            continue

        scheme_type = scheme.get("type", "").lower()

        # Check SCHEME_HEADERS mapping
        if scheme_type in SCHEME_HEADERS:
            required.update(SCHEME_HEADERS[scheme_type])
        elif scheme_type == "apikey":
            # apiKey: use the name field, default to x-api-key
            header_name = scheme.get("name", "x-api-key").lower()
            if scheme.get("in", "header") == "header":
                required.add(header_name)
        else:
            # Unknown scheme, require authorization header as fallback
            required.add("authorization")

    return required


def get_acceptance_refs(contract: Dict) -> List[str]:
    """Extract acceptance references from contract."""
    metadata = contract.get("x-artifact-metadata", {})
    traceability = metadata.get("traceability", {})
    return traceability.get("acceptance_refs", [])


def _resolve_schema_ref(contract: Dict, schema_ref: str) -> Optional[Dict]:
    """Resolve $ref to actual schema definition."""
    if not isinstance(schema_ref, str):
        return None
    if not schema_ref.startswith("#/definitions/"):
        return None
    definition_name = schema_ref.split("/")[-1]
    return contract.get("definitions", {}).get(definition_name)


def _extract_field_names(schema: Dict, contract: Dict, visited: Optional[Set[str]] = None) -> Set[str]:
    """Recursively extract all field names from a schema."""
    if visited is None:
        visited = set()

    fields = set()

    if not isinstance(schema, dict):
        return fields

    # Handle $ref
    ref = schema.get("$ref")
    if ref:
        if ref in visited:
            return fields
        visited.add(ref)
        resolved = _resolve_schema_ref(contract, ref)
        if resolved:
            fields.update(_extract_field_names(resolved, contract, visited))
        return fields

    # Extract property names
    properties = schema.get("properties", {})
    if isinstance(properties, dict):
        fields.update(properties.keys())
        for prop_schema in properties.values():
            if isinstance(prop_schema, dict):
                fields.update(_extract_field_names(prop_schema, contract, visited))

    # Handle items in arrays
    items = schema.get("items")
    if isinstance(items, dict):
        fields.update(_extract_field_names(items, contract, visited))

    # Handle allOf, anyOf, oneOf
    for combinator in ("allOf", "anyOf", "oneOf"):
        combined = schema.get(combinator, [])
        if isinstance(combined, list):
            for sub_schema in combined:
                if isinstance(sub_schema, dict):
                    fields.update(_extract_field_names(sub_schema, contract, visited))

    return fields


def soft_fail_or_fail(message: str, issues: List[str]):
    """Fail test or soft-fail (xfail) based on ATDD_SECURITY_ENFORCE env var."""
    full_message = (
        f"{message}:\n" +
        "\n".join(f"  {issue}" for issue in issues[:10]) +
        (f"\n  ... and {len(issues) - 10} more" if len(issues) > 10 else "")
    )

    if ENFORCE_SECURITY:
        pytest.fail(full_message)
    else:
        pytest.xfail(
            f"[SOFT-FAIL] {full_message}\n\n"
            "Set ATDD_SECURITY_ENFORCE=1 to enforce."
        )


@pytest.mark.tester
@pytest.mark.security
def test_secured_operations_have_required_headers():
    """
    SPEC-TESTER-SEC-0001: Secured operations must declare auth headers

    Given: Contract schemas with security requirements
    When: Checking for header declarations
    Then: Secured operations must include appropriate auth header based on scheme

    Security scheme to header mapping:
    - jwt/bearer/oauth2/http: authorization
    - apiKey: dynamic (from security[].name, default x-api-key)
    """
    contract_files = find_all_contract_schemas()

    if not contract_files:
        pytest.skip("No contract schema files found")

    missing_headers = []

    for contract_path in contract_files:
        contract = load_contract(contract_path)
        if not contract:
            continue

        metadata = contract.get("x-artifact-metadata", {})
        api = metadata.get("api", {})
        operations = api.get("operations", [])

        # Check each secured operation
        for op in operations:
            if not isinstance(op, dict):
                continue

            security = op.get("security", [])
            if not security:
                continue  # Not a secured operation

            required_headers = get_required_headers_for_security(security)
            declared_headers = get_operation_headers(op)

            # Also check contract-level headers
            declared_headers.update(get_declared_headers(contract))

            if not declared_headers.intersection(required_headers):
                op_desc = f"{op.get('method', '?')} {op.get('path', '?')}"
                missing_headers.append(
                    f"{contract_path.relative_to(REPO_ROOT)} [{op_desc}]: "
                    f"Secured operation missing auth header. "
                    f"Declared: {sorted(declared_headers) or 'none'}. "
                    f"Required one of: {sorted(required_headers)}"
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
          (either security: [] for public or security: [{...}] for protected)

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

        api = metadata.get("api", {})
        operations = api.get("operations", [])

        # Check each operation for explicit security
        for op in operations:
            if not isinstance(op, dict):
                continue

            # security field must be present (even if empty array for public)
            if "security" not in op:
                op_desc = f"{op.get('method', '?')} {op.get('path', '?')}"
                missing_security.append(
                    f"{contract_path.relative_to(REPO_ROOT)} [{op_desc}]: "
                    f"Operation missing explicit security field. "
                    f"Add security: [] for public or security: [{{...}}] for protected"
                )

        # Also check for legacy x-artifact-metadata.security pattern
        if not operations:
            security = metadata.get("security", {})
            has_explicit_security = (
                "requires_auth" in security or
                "authentication" in security or
                "securitySchemes" in contract or
                api.get("security")
            )

            if not has_explicit_security:
                missing_security.append(
                    f"{contract_path.relative_to(REPO_ROOT)}: "
                    f"API contract missing explicit security declaration. "
                    f"Add x-artifact-metadata.api.operations[].security"
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


@pytest.mark.tester
@pytest.mark.security
def test_error_responses_have_no_sensitive_fields():
    """
    SPEC-TESTER-SEC-0004: Error responses should not expose sensitive data.

    Given: Contract schemas with error response definitions
    When: Checking 4xx/5xx response schemas
    Then: Response schemas should not contain sensitive field names

    Mode: warning only (pytest.xfail, not hard fail)

    Sensitive fields: password, secret, credential, ssn, api_key, private_key, token
    Allowed exceptions: error_key, key_id, token_type
    """
    contract_files = find_all_contract_schemas()

    if not contract_files:
        pytest.skip("No contract schema files found")

    sensitive_exposures = []

    for contract_path in contract_files:
        contract = load_contract(contract_path)
        if not contract:
            continue

        metadata = contract.get("x-artifact-metadata", {})
        api = metadata.get("api", {})
        operations = api.get("operations", [])

        for op in operations:
            if not isinstance(op, dict):
                continue

            responses = op.get("responses", {})
            if not isinstance(responses, dict):
                continue

            # Check 4xx and 5xx responses
            for status_code, response in responses.items():
                if not isinstance(status_code, str):
                    continue

                # Only check error responses (4xx, 5xx)
                if not (status_code.startswith("4") or status_code.startswith("5")):
                    continue

                if not isinstance(response, dict):
                    continue

                schema = response.get("schema", {})
                if not schema:
                    continue

                # Handle $ref - can be string or dict with $ref key
                if isinstance(schema, str):
                    resolved = _resolve_schema_ref(contract, schema)
                    if resolved:
                        schema = resolved
                    else:
                        continue  # Can't resolve, skip
                elif isinstance(schema, dict) and "$ref" in schema:
                    resolved = _resolve_schema_ref(contract, schema["$ref"])
                    if resolved:
                        schema = resolved

                # Extract all field names from the schema
                field_names = _extract_field_names(schema, contract)

                # Check for sensitive fields
                for field in field_names:
                    field_lower = field.lower()
                    # Check if field matches sensitive patterns
                    for sensitive in SENSITIVE_FIELDS:
                        if sensitive in field_lower and field_lower not in ALLOWED_IN_ERRORS:
                            op_desc = f"{op.get('method', '?')} {op.get('path', '?')}"
                            sensitive_exposures.append(
                                f"{contract_path.relative_to(REPO_ROOT)} [{op_desc}] {status_code}: "
                                f"Error response contains potentially sensitive field '{field}'"
                            )
                            break

    if sensitive_exposures:
        # This is warning-only mode, always xfail
        pytest.xfail(
            f"[WARNING] Found {len(sensitive_exposures)} error responses with potentially sensitive fields:\n" +
            "\n".join(f"  {exp}" for exp in sensitive_exposures[:10]) +
            (f"\n  ... and {len(sensitive_exposures) - 10} more" if len(sensitive_exposures) > 10 else "") +
            "\n\nReview these fields to ensure no sensitive data is exposed in error responses."
        )
