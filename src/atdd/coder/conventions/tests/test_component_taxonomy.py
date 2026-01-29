"""
Tests for component taxonomy adoption in conventions.

Tests SPEC-CODER-CONV-0006 through SPEC-CODER-CONV-0011
ATDD: Validates that conventions use generic component types with examples.
"""
import pytest
import yaml
from pathlib import Path
from typing import Dict, Any, List


# Utility functions for loading YAML files
def load_yaml(file_path: Path) -> Dict[str, Any]:
    """Load and parse a YAML file."""
    with open(file_path, 'r') as f:
        return yaml.safe_load(f)


def get_project_root() -> Path:
    """Get the project root directory."""
    # From tests/ directory, go up 4 levels: tests -> conventions -> coder -> atdd -> root
    return Path(__file__).parent.parent.parent.parent.parent


def load_convention_backend() -> Dict[str, Any]:
    """Load the backend convention."""
    conventions_dir = Path(__file__).parent.parent
    path = conventions_dir / "backend.convention.yaml"
    return load_yaml(path)


def load_convention_frontend() -> Dict[str, Any]:
    """Load the frontend convention."""
    conventions_dir = Path(__file__).parent.parent
    path = conventions_dir / "frontend.convention.yaml"
    return load_yaml(path)


def get_component_type_names(layer_data: Dict[str, Any]) -> List[str]:
    """Extract component type names from a layer."""
    component_types = layer_data.get("component_types", [])
    return [ct["name"] for ct in component_types]


# Expected generic component types for validation
BACKEND_GENERIC_TYPES = {
    "presentation": ["controllers", "routes", "serializers", "validators", "middleware", "guards", "views"],
    "application": ["use_cases", "handlers", "ports", "dtos", "policies", "workflows"],
    "domain": ["entities", "value_objects", "aggregates", "services", "specifications", "events", "exceptions"],
    "integration": ["repositories", "clients", "caches", "engines", "formatters", "notifiers", "queues", "stores", "mappers", "schedulers", "monitors"]
}

FRONTEND_GENERIC_TYPES = {
    "presentation": ["views", "components", "containers", "controllers", "routes", "layouts", "styles", "animations", "forms", "hooks", "directives", "filters"],
    "application": ["use_cases", "ports", "policies", "dtos"],
    "domain": ["entities", "value_objects", "services", "specifications", "exceptions"],
    "integration": ["repositories", "clients", "stores", "serializers", "mappers", "interceptors", "caches", "synchronizers", "monitors", "validators", "workers", "connectors"]
}


class TestBackendConventionAdoptsTaxonomy:
    """Test SPEC-CODER-CONV-0006: Backend convention uses generic component types"""

    def test_backend_convention_adopts_taxonomy_types(self):
        """Should have generic component types with examples for all 4 layers"""
        convention = load_convention_backend()
        backend = convention.get("backend", {})
        layers = backend.get("layers", {})

        for layer_name, expected_types in BACKEND_GENERIC_TYPES.items():
            layer = layers.get(layer_name, {})
            actual_types = get_component_type_names(layer)

            # Verify all generic types are present
            for expected_type in expected_types:
                assert expected_type in actual_types, \
                    f"{layer_name} layer missing generic type '{expected_type}'"

            # Verify each component type has required fields
            component_types = layer.get("component_types", [])
            for ct in component_types:
                assert "name" in ct, f"Component type missing 'name' field"
                assert "description" in ct, f"Component type {ct.get('name')} missing 'description'"
                assert "suffix" in ct, f"Component type {ct.get('name')} missing 'suffix'"
                assert "examples" in ct, f"Component type {ct.get('name')} missing 'examples'"
                assert len(ct["examples"]) > 0, f"Component type {ct.get('name')} has empty examples"


class TestFrontendConventionAdoptsTaxonomy:
    """Test SPEC-CODER-CONV-0007: Frontend convention uses generic component types"""

    def test_frontend_convention_adopts_taxonomy_types(self):
        """Should have generic component types with examples for all 4 layers"""
        convention = load_convention_frontend()
        frontend = convention.get("frontend", {})
        layers = frontend.get("layers", {})

        for layer_name, expected_types in FRONTEND_GENERIC_TYPES.items():
            layer = layers.get(layer_name, {})
            actual_types = get_component_type_names(layer)

            # Verify all generic types are present
            for expected_type in expected_types:
                assert expected_type in actual_types, \
                    f"{layer_name} layer missing generic type '{expected_type}'"

            # Verify each component type has required fields
            component_types = layer.get("component_types", [])
            for ct in component_types:
                assert "name" in ct, f"Component type missing 'name' field"
                assert "description" in ct, f"Component type {ct.get('name')} missing 'description'"
                assert "suffix" in ct, f"Component type {ct.get('name')} missing 'suffix'"
                assert "examples" in ct, f"Component type {ct.get('name')} missing 'examples'"
                assert len(ct["examples"]) > 0, f"Component type {ct.get('name')} has empty examples"


class TestBackendPreservesDependencyRules:
    """Test SPEC-CODER-CONV-0008: Backend convention preserves dependency rules and CI enforcement"""

    def test_backend_preserves_dependency_rules(self):
        """Should preserve dependency.allowed_edges, forbidden_examples, and ci_enforcement sections"""
        convention = load_convention_backend()
        backend = convention.get("backend", {})

        # Verify dependency section exists
        dependency = backend.get("dependency", {})
        assert dependency is not None, "Backend dependency section missing"

        # Verify allowed_edges preserved
        allowed_edges = dependency.get("allowed_edges", [])
        assert len(allowed_edges) > 0, "Backend allowed_edges empty or missing"

        # Check specific expected edges
        edge_from_values = [edge.get("from") for edge in allowed_edges]
        assert "presentation" in edge_from_values, "Missing presentation edge"
        assert "application" in edge_from_values, "Missing application edge"
        assert "integration" in edge_from_values, "Missing integration edge"

        # Verify forbidden_examples preserved
        forbidden_examples = dependency.get("forbidden_examples", [])
        assert len(forbidden_examples) > 0, "Backend forbidden_examples empty or missing"

        # Verify ci_enforcement section exists
        ci_enforcement = backend.get("ci_enforcement", {})
        assert ci_enforcement is not None, "Backend ci_enforcement section missing"

        # Verify ci_enforcement has required subsections
        checks = ci_enforcement.get("checks", [])
        assert len(checks) > 0, "Backend ci_enforcement.checks empty or missing"

        tools = ci_enforcement.get("tools", [])
        assert len(tools) > 0, "Backend ci_enforcement.tools empty or missing"

        failure_policy = ci_enforcement.get("failure_policy")
        assert failure_policy is not None, "Backend ci_enforcement.failure_policy missing"


class TestFrontendPreservesDependencyRules:
    """Test SPEC-CODER-CONV-0009: Frontend convention preserves dependency rules and CI enforcement"""

    def test_frontend_preserves_dependency_rules(self):
        """Should preserve dependency.allowed_edges, forbidden_examples, and ci_enforcement sections"""
        convention = load_convention_frontend()
        frontend = convention.get("frontend", {})

        # Verify dependency section exists
        dependency = frontend.get("dependency", {})
        assert dependency is not None, "Frontend dependency section missing"

        # Verify allowed_edges preserved
        allowed_edges = dependency.get("allowed_edges", [])
        assert len(allowed_edges) > 0, "Frontend allowed_edges empty or missing"

        # Check specific expected edges
        edge_from_values = [edge.get("from") for edge in allowed_edges]
        assert "presentation" in edge_from_values, "Missing presentation edge"
        assert "application" in edge_from_values, "Missing application edge"
        assert "integration" in edge_from_values, "Missing integration edge"

        # Verify forbidden_examples preserved
        forbidden_examples = dependency.get("forbidden_examples", [])
        assert len(forbidden_examples) > 0, "Frontend forbidden_examples empty or missing"

        # Verify ci_enforcement section exists
        ci_enforcement = frontend.get("ci_enforcement", {})
        assert ci_enforcement is not None, "Frontend ci_enforcement section missing"

        # Verify ci_enforcement has required subsections
        checks = ci_enforcement.get("checks", [])
        assert len(checks) > 0, "Frontend ci_enforcement.checks empty or missing"

        tools = ci_enforcement.get("tools", [])
        assert len(tools) > 0, "Frontend ci_enforcement.tools empty or missing"

        failure_policy = ci_enforcement.get("failure_policy")
        assert failure_policy is not None, "Frontend ci_enforcement.failure_policy missing"


class TestTaxonomyUsesGenericNames:
    """Test SPEC-CODER-CONV-0010: Component types have generic names with example arrays"""

    def test_taxonomy_uses_generic_names_with_examples(self):
        """Should verify conventions use generic names with examples arrays"""
        backend_convention = load_convention_backend()
        frontend_convention = load_convention_frontend()

        # Test backend convention
        backend = backend_convention.get("backend", {})
        layers = backend.get("layers", {})
        integration_layer = layers.get("integration", {})
        component_types = integration_layer.get("component_types", [])

        # Verify generic component types exist with examples
        generic_types = ["repositories", "engines", "formatters", "clients", "caches"]
        found_types = {ct["name"] for ct in component_types}

        for generic_type in generic_types:
            assert generic_type in found_types, f"Generic type '{generic_type}' not found in backend convention"

            # Find the component type and verify it has examples
            ct = next((ct for ct in component_types if ct["name"] == generic_type), None)
            assert ct is not None, f"Component type {generic_type} not found"
            assert "examples" in ct, f"Component type {generic_type} missing examples array"
            assert len(ct["examples"]) > 0, f"Component type {generic_type} has empty examples array"
            assert "description" in ct, f"Component type {generic_type} missing description"

        # Test frontend convention
        frontend = frontend_convention.get("frontend", {})
        layers = frontend.get("layers", {})
        presentation_layer = layers.get("presentation", {})
        component_types = presentation_layer.get("component_types", [])

        # Verify generic component types exist with examples
        generic_types = ["views", "components", "controllers"]
        found_types = {ct["name"] for ct in component_types}

        for generic_type in generic_types:
            assert generic_type in found_types, f"Generic type '{generic_type}' not found in frontend convention"

            # Find the component type and verify it has examples
            ct = next((ct for ct in component_types if ct["name"] == generic_type), None)
            assert ct is not None, f"Component type {generic_type} not found"
            assert "examples" in ct, f"Component type {generic_type} missing examples array"
            assert len(ct["examples"]) > 0, f"Component type {generic_type} has empty examples array"
            assert "description" in ct, f"Component type {generic_type} missing description"


class TestConventionsExcludeUrnAndOrganization:
    """Test SPEC-CODER-CONV-0011: Conventions exclude URN and organization sections"""

    def test_conventions_exclude_urn_and_organization(self):
        """Should verify conventions don't have urn_pattern, urn_examples, organization, or framework_adaptations"""
        backend_convention = load_convention_backend()
        frontend_convention = load_convention_frontend()

        # Test backend convention
        assert "urn_pattern" not in backend_convention, "Backend convention should not have urn_pattern"
        assert "urn_examples" not in backend_convention, "Backend convention should not have urn_examples"
        assert "organization" not in backend_convention, "Backend convention should not have organization section"
        assert "framework_adaptations" not in backend_convention, "Backend convention should not have framework_adaptations"

        # Test frontend convention
        assert "urn_pattern" not in frontend_convention, "Frontend convention should not have urn_pattern"
        assert "urn_examples" not in frontend_convention, "Frontend convention should not have urn_examples"
        assert "organization" not in frontend_convention, "Frontend convention should not have organization section"
        assert "framework_adaptations" not in frontend_convention, "Frontend convention should not have framework_adaptations"

        # Verify conventions only have expected top-level keys
        expected_backend_keys = {"version", "name", "description", "backend"}
        actual_backend_keys = set(backend_convention.keys())
        assert actual_backend_keys == expected_backend_keys, \
            f"Backend convention has unexpected keys: {actual_backend_keys - expected_backend_keys}"

        expected_frontend_keys = {"version", "name", "description", "frontend"}
        actual_frontend_keys = set(frontend_convention.keys())
        assert actual_frontend_keys == expected_frontend_keys, \
            f"Frontend convention has unexpected keys: {actual_frontend_keys - expected_frontend_keys}"
