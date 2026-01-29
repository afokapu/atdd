"""
RED Tests for Artifact Naming Convention with Optional Category Facet

SPEC: SPEC-TESTER-CONV-0059 through SPEC-TESTER-CONV-0067
Feature: Artifact naming supports optional category facet
Background:
  - Colon separator denotes hierarchy (domain:resource)
  - Dot separator denotes facet (resource.category)
  - Category is optional third segment for nested resources
  - Examples use ux:foundations instead of legacy design:tokens
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
def test_logical_pattern_has_category(artifact_convention):
    """Logical naming pattern supports optional category"""
    naming = artifact_convention.get("naming", {})
    logical_pattern = naming.get("logical_pattern")

    assert logical_pattern == "{domain}:{resource}[.{category}]", \
        f"Expected logical_pattern to be '{{domain}}:{{resource}}[.{{category}}]', got: {logical_pattern}"

    # Verify rationale explains hierarchy vs facet
    rationale = naming.get("rationale", "")
    assert "colon" in rationale.lower() or "hierarchy" in rationale.lower(), \
        "Rationale should explain colon separator for hierarchy"


# SPEC-TESTER-CONV-0060
def test_physical_pattern_has_category_directory(artifact_convention):
    """Physical path pattern supports nested category directory"""
    naming = artifact_convention.get("naming", {})
    physical_pattern = naming.get("physical_pattern")

    assert physical_pattern == "contracts/{domain}/{resource}[/{category}].json", \
        f"Expected physical_pattern with optional category directory, got: {physical_pattern}"

    # Check examples demonstrate both patterns
    examples = naming.get("examples", [])
    assert len(examples) >= 2, "Should have examples for both base and category resources"


# SPEC-TESTER-CONV-0061
def test_examples_use_ux_foundations(artifact_convention):
    """Examples use ux:foundations instead of design:tokens"""
    naming = artifact_convention.get("naming", {})
    examples = naming.get("examples", [])

    # Check for ux:foundations base example
    ux_base = None
    ux_category = None

    for example in examples:
        if example.get("logical") == "ux:foundations":
            ux_base = example
        if example.get("logical") == "ux:foundations.colors":
            ux_category = example

    assert ux_base is not None, "Missing ux:foundations base example"
    assert ux_base.get("physical") == "contracts/commons/ux/foundations.json", \
        f"ux:foundations should map to contracts/commons/ux/foundations.json"

    assert ux_category is not None, "Missing ux:foundations.colors category example"
    assert ux_category.get("physical") == "contracts/commons/ux/foundations/colors.json", \
        f"ux:foundations.colors should map to contracts/commons/ux/foundations/colors.json"


# SPEC-TESTER-CONV-0061 (part 2)
def test_no_design_tokens_examples(artifact_convention):
    """No design:tokens examples remain"""
    naming = artifact_convention.get("naming", {})
    examples = naming.get("examples", [])

    for example in examples:
        logical = example.get("logical", "")
        assert not logical.startswith("design:"), \
            f"Found legacy design:tokens example: {logical}"


# SPEC-TESTER-CONV-0062
def test_api_pattern_has_category_segment(artifact_convention):
    """API mapping supports optional category path segment"""
    api_mapping = artifact_convention.get("api_mapping", {})
    pattern = api_mapping.get("pattern")

    assert pattern == "/{domain}s/{id}/{resource}[/{category}]", \
        f"Expected API pattern with optional category segment, got: {pattern}"


# SPEC-TESTER-CONV-0062 (part 2)
def test_api_examples_include_ux_foundations(artifact_convention):
    """API examples include ux:foundations"""
    api_mapping = artifact_convention.get("api_mapping", {})
    examples = api_mapping.get("examples", [])

    # Check for ux:foundations base example
    ux_base = None
    ux_category = None

    for example in examples:
        if example.get("artifact") == "ux:foundations":
            ux_base = example
        if example.get("artifact") == "ux:foundations.colors":
            ux_category = example

    assert ux_base is not None, "Missing ux:foundations API example"
    assert ux_base.get("endpoint") == "GET /uxs/{id}/foundations", \
        f"Expected 'GET /uxs/{{id}}/foundations', got: {ux_base.get('endpoint')}"

    assert ux_category is not None, "Missing ux:foundations.colors API example"
    assert ux_category.get("endpoint") == "GET /uxs/{id}/foundations/colors", \
        f"Expected 'GET /uxs/{{id}}/foundations/colors', got: {ux_category.get('endpoint')}"


# SPEC-TESTER-CONV-0063
def test_urn_pattern_preserves_category_facet(artifact_convention):
    """URN pattern preserves category as dot facet"""
    # Check if artifact_urns section exists
    artifact_urns = artifact_convention.get("artifact_urns", {})
    urn_pattern = artifact_urns.get("urn_pattern", {})

    format_str = urn_pattern.get("format")
    assert format_str == "contract:{domain}:{resource}[.{category}]", \
        f"Expected URN format 'contract:{{domain}}:{{resource}}[.{{category}}]', got: {format_str}"

    # Check conversion rule
    conversion_rule = urn_pattern.get("conversion_rule", "")
    assert "colon" in conversion_rule.lower() and "hierarchy" in conversion_rule.lower(), \
        "Conversion rule should explain colon for hierarchy"
    assert "dot" in conversion_rule.lower() and "facet" in conversion_rule.lower(), \
        "Conversion rule should explain dot for facet"


# SPEC-TESTER-CONV-0063 (part 2)
def test_urn_examples_use_ux_foundations(artifact_convention):
    """URN examples use ux:foundations"""
    artifact_urns = artifact_convention.get("artifact_urns", {})
    examples = artifact_urns.get("examples", {})
    artifact_to_urn = examples.get("artifact_to_urn", [])

    # Check for ux:foundations examples
    ux_base = None
    ux_category = None

    for example in artifact_to_urn:
        if example.get("artifact_name") == "ux:foundations":
            ux_base = example
        if example.get("artifact_name") == "ux:foundations.colors":
            ux_category = example

    assert ux_base is not None, "Missing ux:foundations URN example"
    assert ux_base.get("urn") == "contract:ux:foundations", \
        f"Expected 'contract:ux:foundations', got: {ux_base.get('urn')}"

    assert ux_category is not None, "Missing ux:foundations.colors URN example"
    assert ux_category.get("urn") == "contract:ux:foundations.colors", \
        f"Expected 'contract:ux:foundations.colors', got: {ux_category.get('urn')}"


# SPEC-TESTER-CONV-0064
def test_contract_id_supports_category(artifact_convention):
    """Contract ID field supports optional category"""
    contract_artifacts = artifact_convention.get("contract_artifacts", {})
    id_field = contract_artifacts.get("id_field")

    assert id_field == "id: {domain}:{resource}[.{category}]:v{version}", \
        f"Expected ID field pattern with optional category, got: {id_field}"

    # Check URN mapping mentions category
    urn_mapping = contract_artifacts.get("urn_mapping", "")
    assert ".{category}" in urn_mapping or "category" in urn_mapping.lower(), \
        "URN mapping should mention category facet"


# SPEC-TESTER-CONV-0064 (part 2)
def test_contract_examples_use_ux_foundations(artifact_convention):
    """Contract examples use ux:foundations"""
    contract_artifacts = artifact_convention.get("contract_artifacts", {})
    examples = contract_artifacts.get("example", [])

    # Check for ux:foundations examples
    ux_base = None
    ux_category = None

    for example in examples:
        if example.get("id") == "ux:foundations:v1":
            ux_base = example
        if example.get("id") == "ux:foundations.colors:v1":
            ux_category = example

    assert ux_base is not None, "Missing ux:foundations contract example"
    assert ux_base.get("path") == "ux/foundations.json", \
        f"Expected 'ux/foundations.json', got: {ux_base.get('path')}"
    assert ux_base.get("producer") == "wagon:maintain-ux", \
        f"Expected producer 'wagon:maintain-ux', got: {ux_base.get('producer')}"

    assert ux_category is not None, "Missing ux:foundations.colors contract example"
    assert ux_category.get("path") == "ux/foundations/colors.json", \
        f"Expected 'ux/foundations/colors.json', got: {ux_category.get('path')}"


# SPEC-TESTER-CONV-0065
def test_wagon_examples_use_maintain_ux(artifact_convention):
    """Wagon artifacts examples updated to maintain-ux"""
    wagon_artifacts = artifact_convention.get("wagon_artifacts", {})
    produce_example = wagon_artifacts.get("produce_example", {})

    wagon_name = produce_example.get("wagon")
    assert wagon_name == "maintain-ux", \
        f"Expected producer wagon 'maintain-ux', got: {wagon_name}"


# SPEC-TESTER-CONV-0065 (part 2)
def test_wagon_produces_ux_foundations(artifact_convention):
    """Wagon produces ux:foundations artifacts"""
    wagon_artifacts = artifact_convention.get("wagon_artifacts", {})
    produce_example = wagon_artifacts.get("produce_example", {})
    produce = produce_example.get("produce", [])

    # Check for ux:foundations and ux:foundations.colors
    ux_base = None
    ux_category = None

    for item in produce:
        if item.get("name") == "ux:foundations":
            ux_base = item
        if item.get("name") == "ux:foundations.colors":
            ux_category = item

    assert ux_base is not None, "Missing ux:foundations in produce"
    assert ux_base.get("urn") == "contract:ux:foundations", \
        f"Expected URN 'contract:ux:foundations', got: {ux_base.get('urn')}"
    assert ux_base.get("to") == "external", \
        f"Expected to='external', got: {ux_base.get('to')}"

    assert ux_category is not None, "Missing ux:foundations.colors in produce"
    assert ux_category.get("urn") == "contract:ux:foundations.colors", \
        f"Expected URN 'contract:ux:foundations.colors', got: {ux_category.get('urn')}"


# SPEC-TESTER-CONV-0066
def test_validation_regex_allows_category(artifact_convention):
    """Validation regex allows optional category facet"""
    import re

    validation = artifact_convention.get("validation", {})
    id_pattern = validation.get("id_pattern")

    assert id_pattern is not None, "Missing id_pattern in validation section"

    # Test the regex against valid patterns
    test_cases = [
        ("ux:foundations:v1", True),
        ("ux:foundations.colors:v1", True),
        ("mechanic:decision.choice:v1", True),
        ("match:result:v2", True),
        ("invalid", False),
        ("no:version", False),
    ]

    for test_input, should_match in test_cases:
        match = re.match(id_pattern, test_input)
        if should_match:
            assert match is not None, \
                f"Pattern '{id_pattern}' should match '{test_input}'"
        else:
            assert match is None, \
                f"Pattern '{id_pattern}' should NOT match '{test_input}'"


# SPEC-TESTER-CONV-0067
def test_migration_note_documents_refactoring(artifact_convention):
    """Migration note documents legacy URN refactoring"""
    artifact_urns = artifact_convention.get("artifact_urns", {})
    migration_strategy = artifact_urns.get("migration_strategy", {})
    refactor_note = migration_strategy.get("refactor_note", "")

    assert refactor_note != "", "Missing refactor_note in migration_strategy"

    # Check for legacy pattern documentation
    assert "contract:{domain}.{resource}" in refactor_note or \
           "domain.resource" in refactor_note.lower(), \
        "Should document legacy pattern with dot separator"

    # Check for new pattern documentation
    assert "contract:{domain}:{resource}" in refactor_note or \
           "domain:resource" in refactor_note.lower(), \
        "Should document new pattern with colon separator"

    # Check for category preservation
    assert "category" in refactor_note.lower() and "dot" in refactor_note.lower(), \
        "Should explain category as dot facet"