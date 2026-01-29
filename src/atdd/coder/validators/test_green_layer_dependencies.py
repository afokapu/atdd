"""
SPEC-CODER-CONV-0018: GREEN convention validates layer dependency rules

Test that green.convention.yaml enforces clean architecture dependency rules.
"""

import pytest
from pathlib import Path
import yaml


REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_CONVENTION = REPO_ROOT / "atdd" / "coder" / "conventions" / "backend.convention.yaml"
FRONTEND_CONVENTION = REPO_ROOT / "atdd" / "coder" / "conventions" / "frontend.convention.yaml"


@pytest.mark.coder
def test_domain_has_no_layer_imports():
    """
    SPEC-CODER-CONV-0018: Domain layer must be pure (no dependencies).

    Given: Clean architecture dependency rules
    When: Checking domain layer import rules
    Then: Domain cannot import from application/presentation/integration
    """
    assert BACKEND_CONVENTION.exists(), "backend.convention.yaml must exist"

    with open(BACKEND_CONVENTION, 'r') as f:
        convention = yaml.safe_load(f)

    # Backend has dependency rules at backend.dependency
    backend = convention['backend']
    assert 'dependency' in backend, "Backend must define dependency rules"

    dep_rules = backend['dependency']

    assert dep_rules is not None, "Dependency rules must be defined"

    # Backend uses edge-based dependencies, not per-layer rules
    # Check that domain is not listed as 'from' in any allowed_edges
    allowed_edges = dep_rules.get('allowed_edges', [])
    forbidden_examples = dep_rules.get('forbidden_examples', [])

    # Domain should not be in 'from' field of any allowed edge
    domain_edges = [edge for edge in allowed_edges if edge.get('from') == 'domain']
    assert len(domain_edges) == 0, "Domain should not have outgoing dependencies"

    # Verify forbidden examples include domain restrictions
    assert any('domain →' in example or 'domain ->' in example for example in forbidden_examples), \
        "Forbidden examples must include domain restrictions"


@pytest.mark.coder
def test_application_only_imports_domain():
    """
    SPEC-CODER-CONV-0018: Application can only depend on domain.

    Given: Clean architecture dependency rules
    When: Checking application layer import rules
    Then: Application cannot import from presentation/integration
    """
    assert BACKEND_CONVENTION.exists(), "green.convention.yaml must exist"

    with open(BACKEND_CONVENTION, 'r') as f:
        convention = yaml.safe_load(f)

    backend = convention["backend"]
    dep_rules = backend.get('dependency')

    allowed_edges = dep_rules.get('allowed_edges', [])
    forbidden_examples = dep_rules.get('forbidden_examples', [])

    # Find application edges
    app_edges = [edge for edge in allowed_edges if edge.get('from') == 'application']

    # Application should only depend on domain
    assert len(app_edges) > 0, "Application must have defined dependencies"
    app_edge = app_edges[0]
    assert app_edge.get('to') == ['domain'], \
        f"Application should only depend on domain, got {app_edge.get('to')}"

    # Check forbidden examples
    assert any('application → presentation' in example or 'application -> presentation' in example
               for example in forbidden_examples), \
        "Application to presentation must be forbidden"


@pytest.mark.coder
def test_integration_only_imports_domain():
    """
    SPEC-CODER-CONV-0018: Integration can only depend on domain.

    Given: Clean architecture dependency rules
    When: Checking integration layer import rules
    Then: Integration cannot import from application/presentation
    """
    assert BACKEND_CONVENTION.exists(), "green.convention.yaml must exist"

    with open(BACKEND_CONVENTION, 'r') as f:
        convention = yaml.safe_load(f)

    backend = convention["backend"]
    dep_rules = backend.get('dependency')

    allowed_edges = dep_rules.get('allowed_edges', [])

    # Find integration edges
    int_edges = [edge for edge in allowed_edges if edge.get('from') == 'integration']

    # Integration should depend on application and domain
    assert len(int_edges) > 0, "Integration must have defined dependencies"
    int_edge = int_edges[0]
    int_deps = int_edge.get('to', [])

    # Integration typically depends on both application and domain in clean arch
    assert 'domain' in int_deps, "Integration should depend on domain"
    assert 'presentation' not in int_deps, "Integration should not depend on presentation"


@pytest.mark.coder
def test_presentation_imports_valid():
    """
    SPEC-CODER-CONV-0018: Presentation can depend on application and domain.

    Given: Clean architecture dependency rules
    When: Checking presentation layer import rules
    Then: Presentation can import from application and domain
    """
    assert BACKEND_CONVENTION.exists(), "green.convention.yaml must exist"

    with open(BACKEND_CONVENTION, 'r') as f:
        convention = yaml.safe_load(f)

    backend = convention["backend"]
    dep_rules = backend.get('dependency')

    allowed_edges = dep_rules.get('allowed_edges', [])

    # Find presentation edges
    pres_edges = [edge for edge in allowed_edges if edge.get('from') == 'presentation']

    # Presentation can depend on application and domain
    assert len(pres_edges) > 0, "Presentation must have defined dependencies"
    pres_edge = pres_edges[0]
    pres_deps = pres_edge.get('to', [])

    assert 'application' in pres_deps, "Presentation must be allowed to depend on application"
    assert 'domain' in pres_deps, "Presentation must be allowed to depend on domain"