"""
SPEC-COACH-UTILS-0291: Add implementation paths array to feature manifest files

Tests updating feature manifests with implementation paths from filesystem.
"""
import pytest
import yaml
from pathlib import Path


def test_update_feature_implementation_paths(tmp_path):
    """
    SPEC-COACH-UTILS-0291: Add implementation paths array to feature manifest files

    Given: Feature manifests exist at plan/{wagon_snake}/features/{feature_snake}.yaml
           Features have URNs in format feature:wagon-slug.feature-slug
           Implementation directories may exist in python/, lib/, supabase/functions/, packages/
           Filesystem uses snake_case for directory names
    When: Updating feature manifests with implementation paths
    Then: Each feature manifest gets a paths array field
          paths array contains only existing implementation directories
          Path format is language_dir/wagon_snake/feature_snake/
          URN kebab-case is converted to filesystem snake_case
          Checks these locations python/, lib/, supabase/functions/, packages/
          Empty array if no implementations exist
          Feature manifests are updated in place
          YAML structure and formatting preserved
    """
    # Setup directory structure
    plan_dir = tmp_path / "plan"
    plan_dir.mkdir()

    # Create wagon directory with features subdirectory
    wagon_dir = plan_dir / "test_wagon"
    wagon_dir.mkdir()
    features_dir = wagon_dir / "features"
    features_dir.mkdir()

    # Create feature manifest
    feature_manifest = features_dir / "test_feature.yaml"
    feature_data = {
        "feature": "test-feature",
        "urn": "feature:test-wagon.test-feature",
        "description": "Test feature for path updates",
        "acceptance": []
    }
    with open(feature_manifest, 'w') as f:
        yaml.dump(feature_data, f, default_flow_style=False, sort_keys=False)

    # Create another feature manifest with no implementations
    feature_no_impl = features_dir / "no_impl_feature.yaml"
    feature_no_impl_data = {
        "feature": "no-impl-feature",
        "urn": "feature:test-wagon.no-impl-feature",
        "description": "Feature with no implementations",
        "acceptance": []
    }
    with open(feature_no_impl, 'w') as f:
        yaml.dump(feature_no_impl_data, f, default_flow_style=False, sort_keys=False)

    # Create some implementation directories (snake_case)
    # Python implementation exists
    python_dir = tmp_path / "python" / "test_wagon" / "test_feature"
    python_dir.mkdir(parents=True)

    # Dart lib implementation exists
    lib_dir = tmp_path / "lib" / "test_wagon" / "test_feature"
    lib_dir.mkdir(parents=True)

    # Supabase functions implementation DOES NOT exist (intentionally)
    # packages implementation DOES NOT exist (intentionally)

    # Import and call the update function
    from atdd.coach.commands.registry import RegistryBuilder

    builder = RegistryBuilder(tmp_path)
    builder.update_feature_implementation_paths()

    # Load the updated feature manifest
    with open(feature_manifest, 'r') as f:
        updated_data = yaml.safe_load(f)

    # Assertions for test_feature
    assert "paths" in updated_data, "Feature manifest should have paths field"
    assert isinstance(updated_data["paths"], list), "paths should be an array"
    assert len(updated_data["paths"]) == 2, "Should have 2 implementation paths (python and lib)"

    expected_python_path = "python/test_wagon/test_feature/"
    expected_lib_path = "lib/test_wagon/test_feature/"

    assert expected_python_path in updated_data["paths"], f"Should contain {expected_python_path}"
    assert expected_lib_path in updated_data["paths"], f"Should contain {expected_lib_path}"

    # Should NOT contain paths that don't exist
    assert "supabase/functions/test_wagon/test_feature/" not in updated_data["paths"]
    assert "packages/test_wagon/test_feature/" not in updated_data["paths"]

    # Other fields should remain unchanged
    assert updated_data["feature"] == "test-feature"
    assert updated_data["urn"] == "feature:test-wagon.test-feature"
    assert updated_data["description"] == "Test feature for path updates"

    # Check feature with no implementations
    with open(feature_no_impl, 'r') as f:
        no_impl_data = yaml.safe_load(f)

    assert "paths" in no_impl_data, "Feature with no impls should still have paths field"
    assert no_impl_data["paths"] == [], "Should have empty paths array when no implementations exist"
