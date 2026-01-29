"""
SPEC-TESTER-CONV-0081: RED convention defines 4-layer test structure for Supabase

Test that red.convention.yaml enforces 4-layer test structure for Supabase.
"""

import pytest
from pathlib import Path
import yaml


REPO_ROOT = Path(__file__).resolve().parents[4]
RED_CONVENTION = REPO_ROOT / "atdd" / "tester" / "conventions" / "red.convention.yaml"


@pytest.mark.tester
def test_red_defines_supabase_layer_structure():
    """
    SPEC-TESTER-CONV-0081: RED convention defines 4-layer test structure for Supabase.

    Given: Supabase structure is supabase/functions/{wagon}/{feature}/
    When: Reading Supabase test structure configuration
    Then: Convention specifies test structure supabase/functions/{wagon}/{feature}/tests/{layer}/
    """
    assert RED_CONVENTION.exists(), "red.convention.yaml must exist"

    with open(RED_CONVENTION, 'r') as f:
        convention = yaml.safe_load(f)

    structure = convention.get('layer_structure') or convention.get('test_structure')
    assert structure is not None, "Convention must define test structure"

    # Check Supabase/TypeScript-specific configuration
    assert 'supabase' in structure or 'typescript' in structure, \
        "Convention must define Supabase/TypeScript test structure"

    supabase_config = structure.get('supabase') or structure.get('typescript')

    # Verify 4 layers are defined
    assert 'layers' in supabase_config, "Supabase config must define layers"
    layers = supabase_config['layers']

    expected_layers = {'presentation', 'application', 'domain', 'integration'}
    assert set(layers) == expected_layers, \
        f"Layers must be {expected_layers}, got {set(layers)}"

    # Verify test path pattern
    assert 'test_path_pattern' in supabase_config, "Supabase config must define test_path_pattern"
    pattern = supabase_config['test_path_pattern']

    assert '{wagon}' in pattern, "Pattern must include {wagon} placeholder"
    assert '{feature}' in pattern, "Pattern must include {feature} placeholder"
    assert '{layer}' in pattern, "Pattern must include {layer} placeholder"
    assert 'tests' in pattern, "Pattern must include 'tests' directory"
    assert 'supabase/functions' in pattern or 'functions' in pattern, \
        "Pattern must reference Supabase functions directory"

    # Verify it matches expected pattern
    expected_pattern = "supabase/functions/{wagon}/{feature}/tests/{layer}/"
    assert pattern == expected_pattern or \
           pattern.startswith("supabase/functions/{wagon}/{feature}/tests/{layer}"), \
        f"Pattern should be {expected_pattern}, got {pattern}"


@pytest.mark.tester
def test_http_tests_in_presentation():
    """
    SPEC-TESTER-CONV-0081: HTTP handler tests go in presentation layer.

    Given: Supabase layer structure
    When: Determining layer for HTTP handler tests
    Then: HTTP tests are placed in presentation layer
    """
    assert RED_CONVENTION.exists(), "red.convention.yaml must exist"

    with open(RED_CONVENTION, 'r') as f:
        convention = yaml.safe_load(f)

    structure = convention.get('layer_structure') or convention.get('test_structure')
    supabase_config = structure.get('supabase') or structure.get('typescript', {})

    # Check for layer mapping rules
    layer_mapping = supabase_config.get('layer_mapping') or supabase_config.get('test_type_layers')

    if layer_mapping:
        # HTTP/controller tests should map to presentation
        assert layer_mapping.get('http') == 'presentation' or \
               layer_mapping.get('controller') == 'presentation' or \
               'http' in layer_mapping.get('presentation', []), \
            "HTTP handler tests must be in presentation layer"