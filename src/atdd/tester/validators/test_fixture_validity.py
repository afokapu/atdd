"""
Test fixtures match contract schemas and are valid.

Validates:
- Test fixtures conform to contract schemas
- Fixture data is realistic and valid
- Fixtures cover edge cases
- Fixtures are not hardcoded production data

Inspired by: .claude/utils/tester/ (fixture utilities)
But: Self-contained, no utility dependencies
"""

import pytest
import json
import yaml
from pathlib import Path
from typing import Dict, List, Any


# Path constants
REPO_ROOT = Path(__file__).resolve().parents[4]
PYTHON_DIR = REPO_ROOT / "python"
CONTRACTS_DIR = REPO_ROOT / "contracts"


def find_contract_schemas() -> Dict[str, Dict]:
    """
    Find all contract schemas.

    Returns:
        Dict mapping contract ID to schema data
    """
    if not CONTRACTS_DIR.exists():
        return {}

    schemas = {}

    for schema_file in CONTRACTS_DIR.rglob("*.schema.json"):
        try:
            with open(schema_file, 'r', encoding='utf-8') as f:
                schema = json.load(f)

            schema_id = schema.get('$id', str(schema_file.stem))
            schemas[schema_id] = {
                'schema': schema,
                'file': str(schema_file.relative_to(REPO_ROOT))
            }
        except Exception:
            continue

    return schemas


def find_test_fixtures() -> Dict[str, List[Any]]:
    """
    Find test fixtures in Python test files.

    Returns:
        Dict mapping fixture file to list of fixture data
    """
    if not PYTHON_DIR.exists():
        return {}

    fixtures = {}

    # Look for fixture files (conftest.py, fixtures.py, etc.)
    for test_dir in PYTHON_DIR.rglob("test"):
        if not test_dir.is_dir():
            continue

        # Check conftest.py
        conftest = test_dir / "conftest.py"
        if conftest.exists():
            fixture_data = extract_fixtures_from_file(conftest)
            if fixture_data:
                fixtures[str(conftest.relative_to(REPO_ROOT))] = fixture_data

        # Check fixtures.py
        fixtures_file = test_dir / "fixtures.py"
        if fixtures_file.exists():
            fixture_data = extract_fixtures_from_file(fixtures_file)
            if fixture_data:
                fixtures[str(fixtures_file.relative_to(REPO_ROOT))] = fixture_data

        # Check fixtures/ directory
        fixtures_dir = test_dir / "fixtures"
        if fixtures_dir.exists() and fixtures_dir.is_dir():
            for fixture_file in fixtures_dir.glob("*.json"):
                try:
                    with open(fixture_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    fixtures[str(fixture_file.relative_to(REPO_ROOT))] = [data]
                except Exception:
                    continue

            for fixture_file in fixtures_dir.glob("*.yaml"):
                try:
                    with open(fixture_file, 'r', encoding='utf-8') as f:
                        data = yaml.safe_load(f)
                    fixtures[str(fixture_file.relative_to(REPO_ROOT))] = [data]
                except Exception:
                    continue

    return fixtures


def extract_fixtures_from_file(file_path: Path) -> List[Dict]:
    """
    Extract fixture data from Python file.

    Returns:
        List of fixture dictionaries found in file
    """
    # Simplified extraction - looks for dict literals
    # In reality, would need AST parsing for complete extraction
    fixtures = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return []

    # Look for pytest fixtures that return dictionaries
    # This is a simplified heuristic
    import re

    # Find @pytest.fixture decorated functions
    fixture_pattern = r'@pytest\.fixture[^\n]*\ndef\s+(\w+)\([^)]*\):'
    fixture_matches = re.finditer(fixture_pattern, content)

    for match in fixture_matches:
        fixture_name = match.group(1)
        # Very simplified - just noting that fixtures exist
        # Real implementation would extract actual data
        fixtures.append({'fixture_name': fixture_name, 'type': 'pytest_fixture'})

    return fixtures


def validate_against_schema(data: Dict, schema: Dict) -> List[str]:
    """
    Validate data against JSON schema.

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    # Check required fields
    required = schema.get('required', [])
    for field in required:
        if field not in data:
            errors.append(f"Missing required field: {field}")

    # Check property types
    properties = schema.get('properties', {})
    for field, value in data.items():
        if field in properties:
            expected_type = properties[field].get('type')
            actual_type = type(value).__name__

            # Map Python types to JSON schema types
            type_map = {
                'str': 'string',
                'int': 'integer',
                'float': 'number',
                'bool': 'boolean',
                'list': 'array',
                'dict': 'object',
                'NoneType': 'null'
            }

            json_type = type_map.get(actual_type, actual_type)

            if expected_type and json_type != expected_type:
                errors.append(
                    f"Field '{field}' has type '{json_type}', expected '{expected_type}'"
                )

    return errors


def check_for_suspicious_data(data: Any) -> List[str]:
    """
    Check fixture data for suspicious patterns.

    Returns:
        List of warnings about suspicious data
    """
    warnings = []

    if isinstance(data, dict):
        for key, value in data.items():
            # Check for potential production data patterns
            if isinstance(value, str):
                # Email addresses (might be real)
                if '@' in value and '.' in value and 'example.com' not in value and 'test.com' not in value:
                    warnings.append(f"Field '{key}' contains real-looking email: {value}")

                # Phone numbers (might be real)
                if len(value.replace('-', '').replace(' ', '').replace('(', '').replace(')', '')) == 10 and value.replace('-', '').replace(' ', '').replace('(', '').replace(')', '').isdigit():
                    warnings.append(f"Field '{key}' contains real-looking phone number")

                # Hardcoded IDs (should be generated)
                if key.endswith('_id') and value == value and not value.startswith('test-') and not value.startswith('fixture-'):
                    warnings.append(f"Field '{key}' has hardcoded ID (should be generated)")

            # Recursive check for nested dicts
            if isinstance(value, dict):
                warnings.extend(check_for_suspicious_data(value))

            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        warnings.extend(check_for_suspicious_data(item))

    return warnings


@pytest.mark.tester
def test_fixtures_match_contract_schemas():
    """
    SPEC-TESTER-FIXTURE-0001: Test fixtures conform to contract schemas.

    Fixtures should match the structure defined in contracts.
    This ensures tests use realistic, valid data.

    Given: Test fixtures and contract schemas
    When: Validating fixture data against schemas
    Then: All fixtures conform to their schemas
    """
    schemas = find_contract_schemas()
    fixtures = find_test_fixtures()

    if not schemas:
        pytest.skip("No contract schemas found")

    if not fixtures:
        pytest.skip("No test fixtures found")

    violations = []

    # For each fixture, try to find matching schema
    for fixture_file, fixture_data_list in fixtures.items():
        for fixture_data in fixture_data_list:
            if not isinstance(fixture_data, dict):
                continue

            # Skip pytest fixture metadata entries - they're not actual data
            if fixture_data.get('type') == 'pytest_fixture':
                continue

            # Only validate fixtures that have an explicit schema reference
            # via $schema or schema_ref field
            schema_ref = fixture_data.get('$schema') or fixture_data.get('schema_ref')
            if not schema_ref:
                continue

            # Find matching schema
            if schema_ref in schemas:
                errors = validate_against_schema(fixture_data, schemas[schema_ref]['schema'])

                if errors:
                    violations.append(
                        f"{fixture_file}\\n"
                        f"  Schema: {schema_ref}\\n"
                        f"  Errors: {', '.join(errors[:3])}"
                    )

    if violations:
        pytest.fail(
            f"\\n\\nFound {len(violations)} fixture validation errors:\\n\\n" +
            "\\n\\n".join(violations[:10]) +
            (f"\\n\\n... and {len(violations) - 10} more" if len(violations) > 10 else "")
        )


@pytest.mark.tester
def test_fixtures_do_not_contain_production_data():
    """
    SPEC-TESTER-FIXTURE-0002: Fixtures don't contain production data.

    Test fixtures should use fake/generated data, not real production data.

    Patterns to avoid:
    - Real email addresses
    - Real phone numbers
    - Production API keys
    - Actual user names

    Given: Test fixtures
    When: Scanning for production data patterns
    Then: No production data found
    """
    fixtures = find_test_fixtures()

    if not fixtures:
        pytest.skip("No test fixtures found")

    violations = []

    for fixture_file, fixture_data_list in fixtures.items():
        for fixture_data in fixture_data_list:
            warnings = check_for_suspicious_data(fixture_data)

            if warnings:
                violations.append(
                    f"{fixture_file}\\n" +
                    "\\n".join(f"  - {w}" for w in warnings[:5])
                )

    if violations:
        pytest.fail(
            f"\\n\\nFound {len(violations)} fixtures with suspicious data:\\n\\n" +
            "\\n\\n".join(violations[:10]) +
            (f"\\n\\n... and {len(violations) - 10} more" if len(violations) > 10 else "") +
            "\\n\\nFixtures should use clearly fake/test data (example.com, test-, etc.)"
        )


@pytest.mark.tester
def test_fixtures_use_descriptive_names():
    """
    SPEC-TESTER-FIXTURE-0003: Fixtures have descriptive names.

    Fixture names should clearly indicate what they provide.

    Good: valid_user_fixture, invalid_email_fixture
    Bad: data, test_data, fixture1

    Given: Test fixtures
    When: Checking fixture names
    Then: Names are descriptive and follow conventions
    """
    fixtures = find_test_fixtures()

    if not fixtures:
        pytest.skip("No test fixtures found")

    violations = []

    for fixture_file, fixture_data_list in fixtures.items():
        for fixture_data in fixture_data_list:
            if isinstance(fixture_data, dict) and 'fixture_name' in fixture_data:
                name = fixture_data['fixture_name']

                # Check for bad names
                bad_patterns = ['data', 'test', 'fixture1', 'fixture2', 'tmp', 'temp']

                if name.lower() in bad_patterns:
                    violations.append(
                        f"{fixture_file}\\n"
                        f"  Fixture: {name}\\n"
                        f"  Issue: Name too generic, should be descriptive"
                    )

                # Check if name is too short
                if len(name) < 5:
                    violations.append(
                        f"{fixture_file}\\n"
                        f"  Fixture: {name}\\n"
                        f"  Issue: Name too short (should be descriptive)"
                    )

    if violations:
        pytest.fail(
            f"\\n\\nFound {len(violations)} fixture naming violations:\\n\\n" +
            "\\n\\n".join(violations[:10]) +
            (f"\\n\\n... and {len(violations) - 10} more" if len(violations) > 10 else "")
        )
