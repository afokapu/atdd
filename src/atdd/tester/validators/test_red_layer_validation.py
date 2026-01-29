"""
SPEC-TESTER-CONV-0082: RED convention rejects tests not in layer structure

Test that red.convention.yaml validates tests are in correct layer directories.
"""

import pytest
from pathlib import Path
import yaml


REPO_ROOT = Path(__file__).resolve().parents[4]
RED_CONVENTION = REPO_ROOT / "atdd" / "tester" / "conventions" / "red.convention.yaml"


@pytest.mark.tester
def test_rejects_non_layered_python_tests():
    """
    SPEC-TESTER-CONV-0082: RED convention rejects Python tests not in layer structure.

    Given: Test file generated outside layer directory
    When: Validating test structure
    Then: Convention validation fails with error message
    """
    assert RED_CONVENTION.exists(), "red.convention.yaml must exist"

    with open(RED_CONVENTION, 'r') as f:
        convention = yaml.safe_load(f)

    structure = convention.get('layer_structure') or convention.get('test_structure')
    assert structure is not None, "Convention must define test structure"

    python_config = structure.get('python', {})

    # Check for validation rules
    validation = python_config.get('validation') or convention.get('validation', {})

    # Should reject tests without layer directory
    assert 'require_layer_directory' in validation or \
           validation.get('enforce_layer_structure') == True, \
        "Convention must enforce layer directory requirement"

    # Check for error message configuration
    assert 'error_messages' in validation or 'messages' in validation, \
        "Convention must define error messages for violations"


@pytest.mark.tester
def test_rejects_non_layered_flutter_tests():
    """
    SPEC-TESTER-CONV-0082: RED convention rejects Flutter tests not in layer structure.

    Given: Flutter test file outside layer directory
    When: Validating test structure
    Then: Convention validation fails
    """
    assert RED_CONVENTION.exists(), "red.convention.yaml must exist"

    with open(RED_CONVENTION, 'r') as f:
        convention = yaml.safe_load(f)

    structure = convention.get('layer_structure') or convention.get('test_structure')
    flutter_config = structure.get('flutter') or structure.get('dart', {})

    validation = flutter_config.get('validation') or convention.get('validation', {})

    # Should reject tests without layer directory
    assert 'require_layer_directory' in validation or \
           validation.get('enforce_layer_structure') == True, \
        "Convention must enforce layer directory requirement for Flutter"


@pytest.mark.tester
def test_rejects_non_layered_supabase_tests():
    """
    SPEC-TESTER-CONV-0082: RED convention rejects Supabase tests not in layer structure.

    Given: Supabase test file outside layer directory
    When: Validating test structure
    Then: Convention validation fails
    """
    assert RED_CONVENTION.exists(), "red.convention.yaml must exist"

    with open(RED_CONVENTION, 'r') as f:
        convention = yaml.safe_load(f)

    structure = convention.get('layer_structure') or convention.get('test_structure')
    supabase_config = structure.get('supabase') or structure.get('typescript', {})

    validation = supabase_config.get('validation') or convention.get('validation', {})

    # Should reject tests without layer directory
    assert 'require_layer_directory' in validation or \
           validation.get('enforce_layer_structure') == True, \
        "Convention must enforce layer directory requirement for Supabase"