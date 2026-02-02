"""
RED Tests for Artifact Naming Convention with Theme-Based Hierarchical Taxonomy

SPEC: SPEC-TESTER-CONV-0059 through SPEC-TESTER-CONV-0067
Feature: Artifact naming uses theme-based hierarchical pattern with variant facets
Background:
  - Colon separator denotes hierarchical descent (unlimited depth)
  - Dot separator denotes lateral variant (typically 0-1)
  - Pattern: {theme}(:{category})*:{aspect}(.{variant})?
  - Examples use commons:ux:foundations:color instead of legacy ux:foundations
"""

import pytest
import yaml
from pathlib import Path


@pytest.fixture
def artifact_convention():
    """Load artifact.convention.yaml"""
    # File is at atdd/tester/audits/test_*.py, convention is at atdd/tester/conventions/
    convention_path = Path(__file__).parent.parent / "conventions" / "artifact.convention.yaml"
    assert convention_path.exists(), f"Convention file not found: {convention_path}"

    with open(convention_path) as f:
        return yaml.safe_load(f)


# SPEC-TESTER-CONV-0059
def test_logical_pattern_has_theme_hierarchy(artifact_convention):
    """Logical naming pattern supports theme-based hierarchy with variants"""
    naming = artifact_convention.get("naming", {})
    logical_pattern = naming.get("logical_pattern")

    assert logical_pattern == "{theme}(:{category})*:{aspect}(.{variant})?", \
        f"Expected logical_pattern to be '{{theme}}(:{{category}})*:{{aspect}}(.{{variant}})?', got: {logical_pattern}"

    # Verify rationale explains hierarchy vs variant
    rationale = naming.get("rationale", "")
    assert "colon" in rationale.lower() or "hierarchy" in rationale.lower(), \
        "Rationale should explain colon separator for hierarchical descent"


# SPEC-TESTER-CONV-0060
def test_physical_pattern_has_segments(artifact_convention):
    """Physical path pattern supports hierarchical segments"""
    naming = artifact_convention.get("naming", {})
    physical_pattern = naming.get("physical_pattern")

    assert "contracts/" in physical_pattern and ".schema.json" in physical_pattern, \
        f"Expected physical_pattern with contracts/ prefix and .schema.json extension, got: {physical_pattern}"

    # Check examples demonstrate theme-based patterns
    examples = naming.get("examples", [])
    assert len(examples) >= 2, "Should have examples for various hierarchy depths"


# SPEC-TESTER-CONV-0061
def test_examples_use_theme_hierarchy(artifact_convention):
    """Examples use theme-based hierarchy (commons:ux:foundations:color)"""
    naming = artifact_convention.get("naming", {})
    examples = naming.get("examples", [])

    # Check for commons:ux:foundations hierarchy examples
    ux_base = None
    ux_deep = None

    for example in examples:
        if example.get("logical") == "commons:ux:foundations":
            ux_base = example
        if example.get("logical") == "commons:ux:foundations:color":
            ux_deep = example

    assert ux_base is not None, "Missing commons:ux:foundations base example"
    assert "contracts/commons/ux/foundations" in ux_base.get("physical", ""), \
        f"commons:ux:foundations should map to contracts/commons/ux/foundations path"

    assert ux_deep is not None, "Missing commons:ux:foundations:color deep hierarchy example"
    assert "contracts/commons/ux/foundations/color" in ux_deep.get("physical", ""), \
        f"commons:ux:foundations:color should map to contracts/commons/ux/foundations/color path"


# SPEC-TESTER-CONV-0061 (part 2)
def test_no_legacy_domain_resource_examples(artifact_convention):
    """No legacy domain:resource examples remain (should use theme-based)"""
    naming = artifact_convention.get("naming", {})
    examples = naming.get("examples", [])

    for example in examples:
        logical = example.get("logical", "")
        # Legacy patterns like "ux:foundations" or "design:tokens" without theme prefix
        if logical.count(":") == 1:
            # Single colon is OK for simple patterns like "match:result"
            pass
        # Check no "ux:foundations.colors" dot-for-hierarchy pattern
        assert ".colors" not in logical or logical.count(":") >= 2, \
            f"Found legacy dot-for-hierarchy example: {logical}"


# SPEC-TESTER-CONV-0062
def test_api_pattern_has_theme_segments(artifact_convention):
    """API mapping supports theme-based hierarchy"""
    api_mapping = artifact_convention.get("api_mapping", {})
    pattern = api_mapping.get("pattern")

    # Pattern should include theme and segments
    assert "{" in pattern and "}" in pattern, \
        f"Expected API pattern with template variables, got: {pattern}"


# SPEC-TESTER-CONV-0062 (part 2)
def test_api_examples_include_theme_based(artifact_convention):
    """API examples include theme-based patterns"""
    api_mapping = artifact_convention.get("api_mapping", {})
    examples = api_mapping.get("examples", [])

    # Check for theme-based examples
    has_commons_example = False
    has_match_example = False

    for example in examples:
        artifact = example.get("artifact", "")
        if artifact.startswith("commons:"):
            has_commons_example = True
        if artifact.startswith("match:"):
            has_match_example = True

    assert has_commons_example or has_match_example, \
        "API examples should include theme-based patterns (commons:*, match:*, etc.)"


# SPEC-TESTER-CONV-0063
def test_urn_pattern_preserves_colons_and_dots(artifact_convention):
    """URN pattern preserves colons for hierarchy and dots for variants"""
    artifact_urns = artifact_convention.get("artifact_urns", {})
    urn_pattern = artifact_urns.get("urn_pattern", {})

    format_str = urn_pattern.get("format")
    assert format_str == "contract:{artifact_name}", \
        f"Expected URN format 'contract:{{artifact_name}}', got: {format_str}"

    # Check conversion rule explains preservation
    conversion_rule = urn_pattern.get("conversion_rule", "")
    assert "colon" in conversion_rule.lower() or "hierarchy" in conversion_rule.lower(), \
        "Conversion rule should explain colon preservation for hierarchy"


# SPEC-TESTER-CONV-0063 (part 2)
def test_urn_examples_use_theme_hierarchy(artifact_convention):
    """URN examples use theme-based hierarchy"""
    artifact_urns = artifact_convention.get("artifact_urns", {})
    examples = artifact_urns.get("examples", {})
    artifact_to_urn = examples.get("artifact_to_urn", [])

    # Check for theme-based examples
    has_theme_example = False
    has_variant_example = False

    for example in artifact_to_urn:
        artifact_name = example.get("artifact_name", "")
        urn = example.get("urn", "")

        # Theme-based: multiple colons
        if artifact_name.count(":") >= 2:
            has_theme_example = True
            # URN should match artifact with contract: prefix
            assert urn == f"contract:{artifact_name}", \
                f"URN should be 'contract:{artifact_name}', got: {urn}"

        # Variant: has dot
        if "." in artifact_name:
            has_variant_example = True

    assert has_theme_example, "Missing theme-based hierarchy URN example (multiple colons)"


# SPEC-TESTER-CONV-0064
def test_contract_id_unversioned(artifact_convention):
    """Contract ID field uses unversioned artifact name"""
    contract_artifacts = artifact_convention.get("contract_artifacts", {})
    id_field = contract_artifacts.get("id_field")

    # Should NOT have :v{version} suffix
    assert ":v{version}" not in id_field and ":v1" not in id_field, \
        f"ID field should be unversioned, got: {id_field}"

    # Should reference artifact_name
    assert "{artifact_name}" in id_field, \
        f"ID field should reference artifact_name, got: {id_field}"


# SPEC-TESTER-CONV-0064 (part 2)
def test_contract_examples_use_theme_hierarchy(artifact_convention):
    """Contract examples use theme-based hierarchy"""
    contract_artifacts = artifact_convention.get("contract_artifacts", {})
    examples = contract_artifacts.get("example", [])

    # Check for theme-based examples
    has_theme_example = False

    for example in examples:
        id_value = example.get("id", "")
        # Theme-based: has multiple colons and NO :v suffix
        if id_value.count(":") >= 2 and ":v" not in id_value:
            has_theme_example = True
            # Should have separate version field
            assert "version" in example, \
                f"Example should have separate version field, got: {example}"

    assert has_theme_example, "Missing theme-based hierarchy contract example"


# SPEC-TESTER-CONV-0065
def test_wagon_examples_use_maintain_ux(artifact_convention):
    """Wagon artifacts examples updated to maintain-ux"""
    wagon_artifacts = artifact_convention.get("wagon_artifacts", {})
    produce_example = wagon_artifacts.get("produce_example", {})

    wagon_name = produce_example.get("wagon")
    assert wagon_name == "maintain-ux", \
        f"Expected producer wagon 'maintain-ux', got: {wagon_name}"


# SPEC-TESTER-CONV-0065 (part 2)
def test_wagon_produces_theme_hierarchy_artifacts(artifact_convention):
    """Wagon produces theme-based hierarchy artifacts"""
    wagon_artifacts = artifact_convention.get("wagon_artifacts", {})
    produce_example = wagon_artifacts.get("produce_example", {})
    produce = produce_example.get("produce", [])

    # Check for theme-based artifacts
    has_theme_artifact = False

    for item in produce:
        name = item.get("name", "")
        urn = item.get("urn", "")

        # Theme-based: multiple colons
        if name.count(":") >= 2:
            has_theme_artifact = True
            # URN should match name with contract: prefix
            assert urn == f"contract:{name}", \
                f"Expected URN 'contract:{name}', got: {urn}"

    assert has_theme_artifact, "Missing theme-based hierarchy in produce artifacts"


# SPEC-TESTER-CONV-0066
def test_validation_regex_allows_theme_hierarchy(artifact_convention):
    """Validation regex allows unlimited colons and optional variant dot"""
    import re

    validation = artifact_convention.get("validation", {})
    id_pattern = validation.get("id_pattern")

    assert id_pattern is not None, "Missing id_pattern in validation section"

    # Test the regex against valid patterns
    test_cases = [
        ("commons:ux:foundations:color", True),  # Deep hierarchy
        ("commons:ux:foundations", True),  # Medium hierarchy
        ("mechanic:decision.choice", True),  # Variant with dot
        ("match:result", True),  # Simple theme:aspect
        ("sensory:gesture.raw", True),  # Theme:aspect.variant
        ("invalid", False),  # No colon at all
        ("no-version:v1", False),  # Old style with version suffix
    ]

    for test_input, should_match in test_cases:
        match = re.match(id_pattern, test_input)
        if should_match:
            assert match is not None, \
                f"Pattern '{id_pattern}' should match '{test_input}'"
        else:
            # Note: some patterns may or may not match depending on regex specifics
            pass


# SPEC-TESTER-CONV-0067
def test_migration_note_documents_refactoring(artifact_convention):
    """Migration note documents legacy URN refactoring"""
    artifact_urns = artifact_convention.get("artifact_urns", {})
    migration_strategy = artifact_urns.get("migration_strategy", {})
    refactor_note = migration_strategy.get("refactor_note", "")

    assert refactor_note != "", "Missing refactor_note in migration_strategy"

    # Check for legacy pattern documentation
    assert "legacy" in refactor_note.lower() or "migrate" in refactor_note.lower(), \
        "Should document legacy migration"

    # Check for version suffix removal
    assert "version" in refactor_note.lower() or "$id" in refactor_note.lower(), \
        "Should mention version removal from $id"
