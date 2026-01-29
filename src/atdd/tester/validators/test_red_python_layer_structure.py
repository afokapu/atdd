"""
SPEC-TESTER-CONV-0079: RED convention defines 4-layer test structure for Python

Test that red.convention.yaml enforces 4-layer test structure for Python.
"""

import pytest
from pathlib import Path
import yaml


REPO_ROOT = Path(__file__).resolve().parents[4]
RED_CONVENTION = REPO_ROOT / "atdd" / "tester" / "conventions" / "red.convention.yaml"


@pytest.mark.tester
def test_red_defines_python_layer_structure():
    """
    SPEC-TESTER-CONV-0079: RED convention defines 4-layer test structure for Python.

    Given: red.convention.yaml exists
    When: Reading Python test structure configuration
    Then: Convention specifies test structure python/{wagon}/{feature}/tests/{layer}/
    """
    assert RED_CONVENTION.exists(), "red.convention.yaml must exist"

    with open(RED_CONVENTION, 'r') as f:
        convention = yaml.safe_load(f)

    # Check for layer structure definition
    assert 'layer_structure' in convention or 'test_structure' in convention, \
        "Convention must define layer_structure or test_structure"

    # Get structure config
    structure = convention.get('layer_structure') or convention.get('test_structure')

    # Check Python-specific configuration
    assert 'python' in structure, "Convention must define Python test structure"

    python_config = structure['python']

    # Verify 4 layers are defined
    assert 'layers' in python_config, "Python config must define layers"
    layers = python_config['layers']

    expected_layers = {'presentation', 'application', 'domain', 'integration'}
    assert set(layers) == expected_layers, \
        f"Layers must be {expected_layers}, got {set(layers)}"

    # Verify test path pattern
    assert 'test_path_pattern' in python_config, "Python config must define test_path_pattern"
    pattern = python_config['test_path_pattern']

    assert '{wagon}' in pattern, "Pattern must include {wagon} placeholder"
    assert '{feature}' in pattern, "Pattern must include {feature} placeholder"
    assert '{layer}' in pattern, "Pattern must include {layer} placeholder"
    assert 'tests' in pattern, "Pattern must include 'tests' directory"

    # Verify it matches expected pattern
    expected_pattern = "python/{wagon}/{feature}/tests/{layer}/"
    assert pattern == expected_pattern or pattern.startswith("python/{wagon}/{feature}/tests/{layer}"), \
        f"Pattern should be {expected_pattern}, got {pattern}"


@pytest.mark.tester
def test_red_creates_layer_directories():
    """
    SPEC-TESTER-CONV-0079: Test path generation creates layer directories automatically.

    Given: red.convention.yaml with layer structure
    When: Generating test paths
    Then: Layer directories are created automatically
    """
    assert RED_CONVENTION.exists(), "red.convention.yaml must exist"

    with open(RED_CONVENTION, 'r') as f:
        convention = yaml.safe_load(f)

    structure = convention.get('layer_structure') or convention.get('test_structure')
    assert structure is not None, "Convention must define test structure"

    python_config = structure.get('python', {})

    # Check for auto-create configuration
    assert 'auto_create_directories' in python_config or \
           python_config.get('behavior', {}).get('create_layer_dirs') == True, \
        "Convention must specify that layer directories are auto-created"