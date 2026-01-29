"""
SPEC-CODER-CONV-0017: GREEN convention defines 4-layer structure for Supabase

Test that green.convention.yaml enforces 4-layer structure for Supabase implementation.
"""

import pytest
from pathlib import Path
import yaml


REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_CONVENTION = REPO_ROOT / "atdd" / "coder" / "conventions" / "backend.convention.yaml"
FRONTEND_CONVENTION = REPO_ROOT / "atdd" / "coder" / "conventions" / "frontend.convention.yaml"


@pytest.mark.coder
def test_green_enforces_supabase_layers():
    """
    SPEC-CODER-CONV-0017: Backend convention enforces 4-layer structure for Supabase.

    Given: Supabase implementation uses supabase/functions/{wagon}/{feature}/
    When: Reading Supabase layer structure configuration
    Then: Convention enforces 4 layer directories under function root
    """
    assert BACKEND_CONVENTION.exists(), "backend.convention.yaml must exist"

    with open(BACKEND_CONVENTION, 'r') as f:
        convention = yaml.safe_load(f)

    backend = convention['backend']
    assert 'structure' in backend, "Backend must define structure"
    structure = backend['structure']

    # Check Supabase/TypeScript-specific configuration
    assert 'supabase' in structure or 'typescript' in structure, \
        "Convention must define Supabase/TypeScript layer structure"

    supabase_config = structure.get('supabase') or structure.get('typescript')

    # Verify 4 layers are defined
    assert 'layers' in supabase_config, "Supabase config must define layers"
    layers = supabase_config['layers']

    expected_layers = {'presentation', 'application', 'domain', 'integration'}
    assert set(layers) == expected_layers, \
        f"Layers must be {expected_layers}, got {set(layers)}"

    # Verify source path pattern
    assert 'src_path_pattern' in supabase_config or 'source_pattern' in supabase_config, \
        "Supabase config must define src_path_pattern"

    pattern = supabase_config.get('src_path_pattern') or supabase_config.get('source_pattern')

    assert '{wagon}' in pattern, "Pattern must include {wagon} placeholder"
    assert '{feature}' in pattern, "Pattern must include {feature} placeholder"
    assert '{layer}' in pattern, "Pattern must include {layer} placeholder"
    assert 'supabase/functions' in pattern or 'functions' in pattern, \
        "Pattern must reference Supabase functions directory"

    # Verify it matches expected pattern
    expected_pattern = "supabase/functions/{wagon}/{feature}/{layer}/"
    assert pattern == expected_pattern or \
           pattern.startswith("supabase/functions/{wagon}/{feature}"), \
        f"Pattern should reference {expected_pattern}, got {pattern}"


@pytest.mark.coder
def test_supabase_index_is_thin():
    """
    SPEC-CODER-CONV-0017: Validates index.ts has no business logic.

    Given: Supabase layer structure with index.ts at root
    When: Checking index.ts constraints
    Then: index.ts contains only adapter code (imports presentation only)
    """
    assert BACKEND_CONVENTION.exists(), "backend.convention.yaml must exist"

    with open(BACKEND_CONVENTION, 'r') as f:
        convention = yaml.safe_load(f)

    backend = convention['backend']
    structure = backend.get('structure', {})
    supabase_config = structure.get('supabase') or structure.get('typescript', {})

    # Check for index.ts rules - might be under entrypoint_rules
    index_rules = supabase_config.get('entrypoint_rules', {}).get('index_ts') or \
                 supabase_config.get('index_constraints')

    if index_rules:
        # index.ts should only import from presentation
        assert 'allowed_imports' in index_rules or 'import_restrictions' in index_rules, \
            "index.ts must have import restrictions"

        allowed = index_rules.get('allowed_imports', [])
        if allowed:
            assert 'presentation' in allowed or './presentation' in str(allowed), \
                "index.ts should only import from presentation layer"

        # index.ts should not contain business logic
        assert 'no_business_logic' in index_rules or \
               index_rules.get('role') == 'thin_adapter', \
            "index.ts must be documented as thin adapter with no business logic"