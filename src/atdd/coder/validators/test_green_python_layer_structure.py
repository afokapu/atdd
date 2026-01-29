"""
SPEC-CODER-CONV-0015: GREEN convention defines 4-layer structure for Python

Test that backend.convention.yaml enforces 4-layer structure for Python implementation.
"""

import pytest
from pathlib import Path
import yaml


REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_CONVENTION = REPO_ROOT / "atdd" / "coder" / "conventions" / "backend.convention.yaml"


@pytest.mark.coder
def test_green_enforces_python_layers():
    """
    SPEC-CODER-CONV-0015: Backend convention enforces 4-layer structure for Python.

    Given: backend.convention.yaml exists
    When: Reading Python layer structure configuration
    Then: Convention enforces 4 layer directories under src/
    """
    assert BACKEND_CONVENTION.exists(), "backend.convention.yaml must exist"

    with open(BACKEND_CONVENTION, 'r') as f:
        convention = yaml.safe_load(f)

    # Backend convention has backend.structure.python
    assert 'backend' in convention, "Convention must have 'backend' section"
    backend = convention['backend']

    assert 'structure' in backend, "Backend must define structure"
    structure = backend['structure']

    # Check Python-specific configuration
    assert 'python' in structure, "Convention must define Python layer structure"

    python_config = structure['python']

    # Verify 4 layers are defined
    assert 'layers' in python_config, "Python config must define layers"
    layers = python_config['layers']

    expected_layers = {'presentation', 'application', 'domain', 'integration'}
    assert set(layers) == expected_layers, \
        f"Layers must be {expected_layers}, got {set(layers)}"

    # Verify source path pattern
    assert 'src_path_pattern' in python_config or 'source_pattern' in python_config, \
        "Python config must define src_path_pattern"

    pattern = python_config.get('src_path_pattern') or python_config.get('source_pattern')

    assert '{wagon}' in pattern, "Pattern must include {wagon} placeholder"
    assert '{feature}' in pattern, "Pattern must include {feature} placeholder"
    assert '{layer}' in pattern, "Pattern must include {layer} placeholder"
    assert 'src' in pattern, "Pattern must include 'src' directory"

    # Verify it matches expected pattern
    expected_pattern = "python/{wagon}/{feature}/src/{layer}/"
    assert pattern == expected_pattern or pattern.startswith("python/{wagon}/{feature}/src/{layer}"), \
        f"Pattern should be {expected_pattern}, got {pattern}"


@pytest.mark.coder
def test_python_component_layer_mapping():
    """
    SPEC-CODER-CONV-0015: Component naming rules map to layers.

    Given: Python layer structure with component types
    When: Checking component-to-layer mapping
    Then: Services in domain, repositories in integration, etc.
    """
    assert BACKEND_CONVENTION.exists(), "backend.convention.yaml must exist"

    with open(BACKEND_CONVENTION, 'r') as f:
        convention = yaml.safe_load(f)

    backend = convention['backend']

    # Backend has layers with component_types that define which components go where
    layers_def = backend.get('layers', {})

    # Check that component types are defined per layer
    assert 'domain' in layers_def, "Domain layer must be defined"
    assert 'integration' in layers_def, "Integration layer must be defined"
    assert 'presentation' in layers_def, "Presentation layer must be defined"
    assert 'application' in layers_def, "Application layer must be defined"

    # Verify component types exist in appropriate layers
    domain_types = [ct['name'] for ct in layers_def['domain'].get('component_types', [])]
    assert 'services' in domain_types, "Services should be in domain layer"

    integration_types = [ct['name'] for ct in layers_def['integration'].get('component_types', [])]
    assert 'repositories' in integration_types, "Repositories should be in integration layer"

    presentation_types = [ct['name'] for ct in layers_def['presentation'].get('component_types', [])]
    assert 'controllers' in presentation_types, "Controllers should be in presentation layer"

    application_types = [ct['name'] for ct in layers_def['application'].get('component_types', [])]
    assert 'use_cases' in application_types, "Use cases should be in application layer"