"""
SPEC-CODER-CONV-0019: GREEN convention enforces cross-stack layer naming consistency

Test that green.convention.yaml enforces same layer names across all stacks.
"""

import pytest
from pathlib import Path
import yaml


REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_CONVENTION = REPO_ROOT / "atdd" / "coder" / "conventions" / "backend.convention.yaml"
FRONTEND_CONVENTION = REPO_ROOT / "atdd" / "coder" / "conventions" / "frontend.convention.yaml"


@pytest.mark.coder
def test_all_stacks_use_same_layer_names():
    """
    SPEC-CODER-CONV-0019: All stacks use same 4 layer names.

    Given: Layer structure defined for Python, Flutter, and Supabase
    When: Checking layer names across stacks
    Then: All use presentation, application, domain, integration
    """
    assert BACKEND_CONVENTION.exists(), "backend.convention.yaml must exist"
    assert FRONTEND_CONVENTION.exists(), "frontend.convention.yaml must exist"

    with open(BACKEND_CONVENTION, 'r') as f:
        backend_conv = yaml.safe_load(f)

    with open(FRONTEND_CONVENTION, 'r') as f:
        frontend_conv = yaml.safe_load(f)

    expected_layers = {'presentation', 'application', 'domain', 'integration'}

    # Check Python (backend)
    backend = backend_conv['backend']
    backend_structure = backend.get('structure', {})
    if 'python' in backend_structure:
        python_layers = set(backend_structure['python'].get('layers', []))
        assert python_layers == expected_layers, \
            f"Python layers {python_layers} must match {expected_layers}"

    # Check Flutter/Dart (frontend)
    frontend = frontend_conv['frontend']
    frontend_structure = frontend.get('structure', {})
    if 'flutter' in frontend_structure or 'dart' in frontend_structure:
        flutter_layers = set(frontend_structure.get('flutter', frontend_structure.get('dart', {})).get('layers', []))
        assert flutter_layers == expected_layers, \
            f"Flutter layers {flutter_layers} must match {expected_layers}"

    # Check Supabase/TypeScript (backend)
    if 'supabase' in backend_structure or 'typescript' in backend_structure:
        supabase_layers = set(backend_structure.get('supabase', backend_structure.get('typescript', {})).get('layers', []))
        assert supabase_layers == expected_layers, \
            f"Supabase layers {supabase_layers} must match {expected_layers}"


@pytest.mark.coder
def test_no_alternative_layer_names():
    """
    SPEC-CODER-CONV-0019: No alternative naming (data, infrastructure) allowed.

    Given: Layer structure configuration
    When: Checking for alternative layer names
    Then: Only presentation, application, domain, integration are allowed
    """
    assert BACKEND_CONVENTION.exists(), "backend.convention.yaml must exist"
    assert FRONTEND_CONVENTION.exists(), "frontend.convention.yaml must exist"

    with open(BACKEND_CONVENTION, 'r') as f:
        backend_conv = yaml.safe_load(f)

    with open(FRONTEND_CONVENTION, 'r') as f:
        frontend_conv = yaml.safe_load(f)

    backend = backend_conv['backend']
    backend_structure = backend.get('structure', {})

    frontend = frontend_conv['frontend']
    frontend_structure = frontend.get('structure', {})

    # Check for forbidden alternatives (could be at convention level or structure level)
    naming_rules = backend.get('naming_rules') or backend_structure.get('naming_rules', {})

    if naming_rules:
        forbidden_names = naming_rules.get('forbidden_layer_names') or \
                         naming_rules.get('disallowed_alternatives', [])

        # Should forbid common alternatives
        alternatives = ['data', 'infrastructure', 'adapters', 'interfaces']
        for alt in alternatives:
            if forbidden_names:
                # At least some alternatives should be explicitly forbidden
                pass  # Convention should document this

    # Alternative: check that only standard names are used
    standard_layers = {'presentation', 'application', 'domain', 'integration'}

    # Check backend stacks
    for stack_name, stack_config in backend_structure.items():
        if isinstance(stack_config, dict) and 'layers' in stack_config:
            layers = set(stack_config['layers'])
            non_standard = layers - standard_layers

            assert len(non_standard) == 0, \
                f"Backend stack {stack_name} has non-standard layers: {non_standard}"

    # Check frontend stacks
    for stack_name, stack_config in frontend_structure.items():
        if isinstance(stack_config, dict) and 'layers' in stack_config:
            layers = set(stack_config['layers'])
            non_standard = layers - standard_layers

            assert len(non_standard) == 0, \
                f"Frontend stack {stack_name} has non-standard layers: {non_standard}"


@pytest.mark.coder
def test_layer_names_lowercase():
    """
    SPEC-CODER-CONV-0019: All layer directory names are lowercase.

    Given: Layer structure configuration
    When: Checking layer name casing
    Then: All layer names are lowercase
    """
    assert BACKEND_CONVENTION.exists(), "backend.convention.yaml must exist"
    assert FRONTEND_CONVENTION.exists(), "frontend.convention.yaml must exist"

    with open(BACKEND_CONVENTION, 'r') as f:
        backend_conv = yaml.safe_load(f)

    with open(FRONTEND_CONVENTION, 'r') as f:
        frontend_conv = yaml.safe_load(f)

    backend = backend_conv['backend']
    backend_structure = backend.get('structure', {})

    frontend = frontend_conv['frontend']
    frontend_structure = frontend.get('structure', {})

    # Check all backend stacks
    for stack_name, stack_config in backend_structure.items():
        if isinstance(stack_config, dict) and 'layers' in stack_config:
            layers = stack_config['layers']

            for layer in layers:
                assert layer == layer.lower(), \
                    f"Layer name '{layer}' in backend {stack_name} must be lowercase"

                # Also check that it doesn't have special characters
                assert layer.replace('_', '').isalnum(), \
                    f"Layer name '{layer}' should be alphanumeric (underscores allowed)"

    # Check all frontend stacks
    for stack_name, stack_config in frontend_structure.items():
        if isinstance(stack_config, dict) and 'layers' in stack_config:
            layers = stack_config['layers']

            for layer in layers:
                assert layer == layer.lower(), \
                    f"Layer name '{layer}' in {stack_name} must be lowercase"

                # Also check that it doesn't have special characters
                assert layer.replace('_', '').isalnum(), \
                    f"Layer name '{layer}' should be alphanumeric (underscores allowed)"