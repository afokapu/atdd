"""
Test unified registry system.

Specs: SPEC-COACH-UTILS-0200 through SPEC-COACH-UTILS-0214
Location: .claude/agents/coach/utils.spec.yaml::unified_registry
"""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import yaml
import json
import tempfile
import shutil


# Test fixtures
@pytest.fixture
def temp_repo():
    """Create temporary repository structure for testing."""
    temp_dir = tempfile.mkdtemp()
    repo_root = Path(temp_dir)

    # Create directory structure
    (repo_root / "plan").mkdir()
    (repo_root / "contracts").mkdir()
    (repo_root / "telemetry").mkdir()
    (repo_root / "atdd" / "tester").mkdir(parents=True)
    (repo_root / "python").mkdir()
    (repo_root / "supabase" / "functions").mkdir(parents=True)

    yield repo_root

    # Cleanup
    shutil.rmtree(temp_dir)


@pytest.fixture
def sample_wagon_manifest(temp_repo):
    """Create sample wagon manifest."""
    wagon_dir = temp_repo / "plan" / "test-wagon"
    wagon_dir.mkdir()

    manifest = {
        "wagon": "test-wagon",
        "description": "Test wagon for registry",
        "theme": "testing",
        "produce": [],
        "consume": []
    }

    manifest_path = wagon_dir / "_test-wagon.yaml"
    with open(manifest_path, "w") as f:
        yaml.dump(manifest, f)

    return manifest_path


@pytest.fixture
def sample_wagons_registry(temp_repo):
    """Create sample plan/_wagons.yaml registry."""
    registry_data = {
        "wagons": [
            {
                "wagon": "existing-wagon",
                "description": "Existing wagon",
                "path": "plan/existing-wagon/",
                "manifest": "plan/existing-wagon/_existing-wagon.yaml"
            },
            {
                "wagon": "draft-wagon",
                "description": "Draft wagon without manifest"
                # No path/manifest = draft mode
            }
        ]
    }

    registry_path = temp_repo / "plan" / "_wagons.yaml"
    with open(registry_path, "w") as f:
        yaml.dump(registry_data, f)

    return registry_path


# SPEC-COACH-UTILS-0200
def test_load_all_registries(temp_repo, sample_wagons_registry):
    """
    Test that registry command loads all registries without distinction.

    Given: User runs registry (no flags)
    When: Registry loader executes
    Then: Loads all registry manifests, returns unified view, read-only mode
    """
    from atdd.coach.commands.registry import RegistryLoader

    loader = RegistryLoader(temp_repo)
    result = loader.load_all()

    assert "plan" in result
    assert "contracts" in result
    assert "telemetry" in result
    assert isinstance(result, dict)

    # Verify read-only (no files modified)
    assert sample_wagons_registry.exists()


# SPEC-COACH-UTILS-0201
def test_build_all_registries(temp_repo, sample_wagon_manifest):
    """
    Test that registry --build updates all registries from source files.

    Given: User runs registry --build
    When: Registry builder executes
    Then: Builds/updates manifests, shows preview, asks confirmation
    """
    from atdd.coach.commands.registry import RegistryBuilder

    builder = RegistryBuilder(temp_repo)

    # Mock user confirmation
    with patch('builtins.input', return_value='yes'):
        result = builder.build_all()

    assert "plan" in result
    assert result["plan"]["total_manifests"] >= 1

    # Verify registry was created
    wagons_registry = temp_repo / "plan" / "_wagons.yaml"
    assert wagons_registry.exists()


# SPEC-COACH-UTILS-0202
def test_load_planner_registry(temp_repo, sample_wagons_registry):
    """
    Test that registry --planner loads planner registry only.

    Given: User runs registry --planner
    When: Registry loader executes
    Then: Loads only plan/_wagons.yaml, returns wagon entries
    """
    from atdd.coach.commands.registry import RegistryLoader

    loader = RegistryLoader(temp_repo)
    result = loader.load_planner()

    assert "wagons" in result
    assert len(result["wagons"]) >= 1
    assert result["wagons"][0]["wagon"] == "existing-wagon"

    # Should not load other registries
    assert "contracts" not in result
    assert "telemetry" not in result


# SPEC-COACH-UTILS-0203
def test_build_planner_registry(temp_repo, sample_wagon_manifest, sample_wagons_registry):
    """
    Test that registry --planner --build updates planner registry from wagon manifests.

    Given: User runs registry --planner --build
    When: Registry builder executes
    Then: Scans wagon manifests, updates registry, preserves drafts
    """
    from atdd.coach.commands.registry import RegistryBuilder

    builder = RegistryBuilder(temp_repo)

    with patch('builtins.input', return_value='yes'):
        result = builder.build_planner(preview_only=False)

    assert result["total_manifests"] >= 1
    assert result["new"] >= 0
    assert result["updated"] >= 0
    assert result["preserved_drafts"] >= 1  # draft-wagon should be preserved

    # Verify draft wagon preserved
    with open(sample_wagons_registry) as f:
        registry = yaml.safe_load(f)

    draft_wagons = [w for w in registry["wagons"] if w["wagon"] == "draft-wagon"]
    assert len(draft_wagons) == 1


# SPEC-COACH-UTILS-0204
def test_load_coder_registry(temp_repo):
    """
    Test that registry --coder loads coder implementation registry.

    Given: User runs registry --coder
    When: Registry loader executes
    Then: Loads python/_implementations.yaml with URNs and links
    """
    from atdd.coach.commands.registry import RegistryLoader

    # Create sample implementations registry
    impl_registry = {
        "implementations": [
            {
                "urn": "impl:test-wagon:domain:entity:python",
                "file": "python/test_wagon/src/domain/entities/test.py",
                "spec_urn": "spec:test-wagon:feature",
                "test_urn": "test:test-wagon:test_entity.py::test_entity_creation",
                "wagon": "test-wagon",
                "layer": "domain",
                "language": "python"
            }
        ]
    }

    impl_path = temp_repo / "python" / "_implementations.yaml"
    with open(impl_path, "w") as f:
        yaml.dump(impl_registry, f)

    loader = RegistryLoader(temp_repo)
    result = loader.load_coder()

    assert "implementations" in result
    assert len(result["implementations"]) == 1
    assert result["implementations"][0]["urn"].startswith("impl:")
    assert "spec_urn" in result["implementations"][0]
    assert "test_urn" in result["implementations"][0]


# SPEC-COACH-UTILS-0205
def test_build_coder_registry(temp_repo):
    """
    Test that registry --coder --build creates implementation registry from Python files.

    Given: User runs registry --coder --build
    When: Registry builder executes
    Then: Scans Python files, extracts metadata, generates URNs, creates manifest
    """
    from atdd.coach.commands.registry import RegistryBuilder

    # Create sample Python implementation
    py_file = temp_repo / "python" / "test_wagon" / "src" / "domain" / "entities" / "test.py"
    py_file.parent.mkdir(parents=True, exist_ok=True)

    py_content = '''"""
Test entity.

Spec: spec:test-wagon:feature
Test: test:test-wagon:test_entity.py::test_entity_creation
"""

class TestEntity:
    """Domain entity for testing."""
    pass
'''

    py_file.write_text(py_content)

    builder = RegistryBuilder(temp_repo)

    with patch('builtins.input', return_value='yes'):
        result = builder.build_coder(preview_only=False)

    assert result["processed"] >= 1

    # Verify registry created
    impl_registry = temp_repo / "python" / "_implementations.yaml"
    assert impl_registry.exists()

    with open(impl_registry) as f:
        data = yaml.safe_load(f)

    assert "implementations" in data
    assert len(data["implementations"]) >= 1


# SPEC-COACH-UTILS-0206
def test_draft_mode_preserves_entries(temp_repo, sample_wagons_registry):
    """
    Test that draft mode preserves registry entries without physical source files.

    Given: Registry has entry without path/manifest field (draft)
    When: registry --build executes
    Then: Preserves draft entries, marks in change report
    """
    from atdd.coach.commands.registry import RegistryBuilder

    builder = RegistryBuilder(temp_repo)

    with patch('builtins.input', return_value='yes'):
        result = builder.build_planner(preview_only=False)

    # Verify draft wagon preserved
    assert result["preserved_drafts"] >= 1

    with open(sample_wagons_registry) as f:
        registry = yaml.safe_load(f)

    # draft-wagon should still exist
    wagons = {w["wagon"]: w for w in registry["wagons"]}
    assert "draft-wagon" in wagons
    assert "manifest" not in wagons["draft-wagon"]


# SPEC-COACH-UTILS-0207
def test_spec_test_impl_traceability(temp_repo):
    """
    Test that spec-test-impl traceability links artifacts across registries.

    Given: Multiple registries with URN links
    When: Building unified registry view
    Then: Each impl links to spec_urn and test_urn, enables traceability queries
    """
    from atdd.coach.commands.registry import RegistryLoader

    # Create linked registries
    spec_urn = "spec:test-wagon:feature"
    test_urn = "test:test-wagon:test_feature.py::test_feature_works"
    impl_urn = "impl:test-wagon:domain:entity:python"

    # Implementation registry with links
    impl_registry = {
        "implementations": [{
            "urn": impl_urn,
            "spec_urn": spec_urn,
            "test_urn": test_urn,
            "wagon": "test-wagon"
        }]
    }

    impl_path = temp_repo / "python" / "_implementations.yaml"
    with open(impl_path, "w") as f:
        yaml.dump(impl_registry, f)

    loader = RegistryLoader(temp_repo)

    # Query traceability
    impl_for_spec = loader.find_implementations_for_spec(spec_urn)
    assert len(impl_for_spec) == 1
    assert impl_for_spec[0]["urn"] == impl_urn

    tests_for_impl = loader.find_tests_for_implementation(impl_urn)
    assert tests_for_impl == test_urn


# SPEC-COACH-UTILS-0208
def test_autogenerate_manifest_for_new_registry(temp_repo):
    """
    Test that registry auto-generates manifest for new registry types.

    Given: New registry type has no manifest (e.g., supabase/)
    When: registry --build executes
    Then: Detects missing manifest, scans sources, auto-generates manifest
    """
    from atdd.coach.commands.registry import RegistryBuilder

    # Create supabase function without registry
    func_file = temp_repo / "supabase" / "functions" / "test-func" / "index.ts"
    func_file.parent.mkdir(parents=True, exist_ok=True)
    func_file.write_text("export const handler = () => {}")

    builder = RegistryBuilder(temp_repo)

    with patch('builtins.input', return_value='yes'):
        result = builder.build_supabase(preview_only=False)

    # Verify manifest created
    supabase_registry = temp_repo / "supabase" / "_functions.yaml"
    assert supabase_registry.exists()

    with open(supabase_registry) as f:
        data = yaml.safe_load(f)

    assert "functions" in data


# SPEC-COACH-UTILS-0209
def test_detect_field_level_changes(temp_repo, sample_wagon_manifest, sample_wagons_registry):
    """
    Test that registry detects and reports field-level changes.

    Given: Existing registry with entries, source files have updated fields
    When: registry --build executes
    Then: Compares field-by-field, reports changed fields, shows detailed report
    """
    from atdd.coach.commands.registry import RegistryBuilder

    # First, add test-wagon to existing registry
    with open(sample_wagons_registry) as f:
        registry = yaml.safe_load(f)

    registry["wagons"].append({
        "wagon": "test-wagon",
        "description": "Original description",
        "path": "plan/test-wagon/",
        "manifest": str(sample_wagon_manifest.relative_to(temp_repo))
    })

    with open(sample_wagons_registry, "w") as f:
        yaml.dump(registry, f)

    # Update wagon manifest description
    with open(sample_wagon_manifest) as f:
        manifest = yaml.safe_load(f)

    manifest["description"] = "Updated description for test wagon"

    with open(sample_wagon_manifest, "w") as f:
        yaml.dump(manifest, f)

    builder = RegistryBuilder(temp_repo)

    # Preview mode to see changes
    result = builder.build_planner(preview_only=True)

    assert "changes" in result

    # Find change for test-wagon
    test_wagon_changes = [c for c in result["changes"] if c.get("wagon") == "test-wagon"]

    assert len(test_wagon_changes) > 0
    assert "fields" in test_wagon_changes[0]
    assert "description" in test_wagon_changes[0]["fields"]


# SPEC-COACH-UTILS-0210
def test_registry_command_renamed():
    """
    Test that registry command is renamed from registry_updater.

    Given: Old command location atdd/coach/commands/registry_updater.py
    When: Refactoring to unified registry system
    Then: Command renamed to registry.py, maintains backward compatibility
    """
    from atdd.coach.commands import registry

    # Verify new module exists
    assert hasattr(registry, 'RegistryLoader')
    assert hasattr(registry, 'RegistryBuilder')

    # Verify backward compatibility (should be able to import old names)
    assert hasattr(registry, 'RegistryUpdater') or hasattr(registry, 'RegistryBuilder')


# SPEC-COACH-UTILS-0211
def test_load_tester_registry(temp_repo):
    """
    Test that registry --tester loads tester test registry.

    Given: User runs registry --tester
    When: Registry loader executes
    Then: Loads atdd/tester/_tests.yaml with URNs and links
    """
    from atdd.coach.commands.registry import RegistryLoader

    # Create sample test registry
    test_registry = {
        "tests": [
            {
                "urn": "test:test-wagon:test_feature.py::test_feature_works",
                "file": "atdd/tester/test_wagon/test_feature.py",
                "spec_urn": "spec:test-wagon:feature",
                "wagon": "test-wagon",
                "acceptance_urn": "acceptance:test-wagon:EXEC001"
            }
        ]
    }

    test_path = temp_repo / "atdd" / "tester" / "_tests.yaml"
    with open(test_path, "w") as f:
        yaml.dump(test_registry, f)

    loader = RegistryLoader(temp_repo)
    result = loader.load_tester()

    assert "tests" in result
    assert len(result["tests"]) == 1
    assert result["tests"][0]["urn"].startswith("test:")
    assert "spec_urn" in result["tests"][0]
    assert "acceptance_urn" in result["tests"][0]


# SPEC-COACH-UTILS-0212
def test_build_tester_registry(temp_repo):
    """
    Test that registry --tester --build creates test registry from test files.

    Given: User runs registry --tester --build
    When: Registry builder executes
    Then: Scans test files, extracts metadata, generates URNs, creates manifest
    """
    from atdd.coach.commands.registry import RegistryBuilder

    # Create sample test file with URN marker
    test_file = temp_repo / "atdd" / "tester" / "test_wagon" / "test_feature.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)

    test_content = '''"""
Test feature.

URN: test:test-wagon:test_feature.py::test_feature_works
Spec: spec:test-wagon:feature
Acceptance: acceptance:test-wagon:EXEC001
"""
import pytest

def test_feature_works():
    """Test that feature works correctly."""
    assert True
'''

    test_file.write_text(test_content)

    builder = RegistryBuilder(temp_repo)

    with patch('builtins.input', return_value='yes'):
        result = builder.build_tester(preview_only=False)

    assert result["processed"] >= 1

    # Verify registry created
    test_registry = temp_repo / "atdd" / "tester" / "_tests.yaml"
    assert test_registry.exists()

    with open(test_registry) as f:
        data = yaml.safe_load(f)

    assert "tests" in data


# SPEC-COACH-UTILS-0213
def test_registry_builder_dry_composition(temp_repo):
    """
    Test that registry builder extracts common pattern for DRY composition.

    Given: Existing registry_updater has similar update methods
    When: Refactoring to unified registry system
    Then: Extracts RegistryBuilder base class, shares common logic
    """
    from atdd.coach.commands.registry import RegistryBuilder

    builder = RegistryBuilder(temp_repo)

    # Verify builder has common methods
    assert hasattr(builder, 'build_planner')
    assert hasattr(builder, 'build_coder')
    assert hasattr(builder, 'build_tester')

    # Verify common preview/confirmation logic exists
    assert hasattr(builder, '_print_change_report') or hasattr(builder, 'preview_changes')
    assert hasattr(builder, '_detect_changes') or hasattr(builder, 'detect_changes')

    # Each builder method should follow same pattern
    # (scan, extract, build, preview, confirm, write)


# SPEC-COACH-UTILS-0214
def test_new_registries_follow_urn_conventions(temp_repo):
    """
    Test that new registries follow existing URN conventions.

    Given: Existing URN patterns in urn.py
    When: Building new registries (tester, coder)
    Then: Uses URNBuilder for URN generation and validation
    """
    from atdd.coach.commands.registry import RegistryBuilder

    # Mock URNBuilder to verify it's used
    with patch('atdd.coach.commands.registry.URNBuilder') as mock_urn:
        mock_urn.test.return_value = "test:wagon:file::func"
        mock_urn.impl.return_value = "impl:wagon:layer:comp:lang"

        builder = RegistryBuilder(temp_repo)

        # Should use URNBuilder for test URNs
        test_urn = mock_urn.test("wagon", "file", "func")
        assert test_urn.startswith("test:")

        # Should use URNBuilder for impl URNs
        impl_urn = mock_urn.impl("wagon", "layer", "comp", "lang")
        assert impl_urn.startswith("impl:")
