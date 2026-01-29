"""
SPEC-CODER-CONV-0013, SPEC-CODER-CONV-0014: Component URN naming migration tests for coder

Tests for migrating component URN pattern in coder conventions.
"""
import pytest
import yaml
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]
COMPONENT_NAMING_PATH = REPO_ROOT / "atdd/coder/conventions/component-naming.convention.yaml"
GREEN_CONV_PATH = REPO_ROOT / "atdd/coder/conventions/green.convention.yaml"


def test_coder_convention_uses_colon_hierarchy():
    """
    SPEC-CODER-CONV-0013: Update coder component-naming.convention.yaml with new URN pattern

    Verify that the URN pattern uses colons for hierarchy.
    """
    with open(COMPONENT_NAMING_PATH) as f:
        convention = yaml.safe_load(f)

    pattern = convention.get("urn_naming", {}).get("pattern", "")

    # Should use colon after wagon and feature
    assert "component:{wagon}:{feature}" in pattern, \
        f"Pattern should use colons for hierarchy: {pattern}"

    # Should NOT use dot between wagon and feature
    assert "component:{wagon}.{feature}" not in pattern, \
        f"Pattern should not use dots between wagon and feature: {pattern}"


def test_coder_artifact_examples_use_new_format():
    """
    SPEC-CODER-CONV-0013: All artifact derivation examples updated with new format

    Verify all artifact_derivation examples use colon-based hierarchy.
    """
    with open(COMPONENT_NAMING_PATH) as f:
        convention = yaml.safe_load(f)

    artifact_derivation = convention.get("artifact_derivation", {})
    # Navigate to the nested structure: rules > capability_suffix > by_artifact_type
    rules = artifact_derivation.get("rules", {})
    capability_suffix = rules.get("capability_suffix", {})
    by_artifact_type = capability_suffix.get("by_artifact_type", {})

    # Collect all example URNs from all artifact types
    all_urns = []
    for artifact_type, config in by_artifact_type.items():
        examples = config.get("examples", [])
        for example in examples:
            urn = example.get("urn", "")
            if urn:
                all_urns.append((artifact_type, urn))

    assert len(all_urns) > 0, "Should have artifact derivation examples"

    for artifact_type, urn in all_urns:
        # Check for colon format (look for pattern: component:word:word)
        # After "component:" there should be wagon, then colon, then feature
        parts = urn.split(":")
        assert len(parts) >= 3, \
            f"URN should have at least 3 colon-separated parts: {urn}"

        # First part should be "component"
        assert parts[0] == "component", f"URN should start with 'component:': {urn}"

        # Should have wagon and feature separated by colon
        # Format: component:wagon:feature.rest
        wagon_feature = f"{parts[1]}:{parts[2].split('.')[0]}"
        assert ":" in wagon_feature, \
            f"{artifact_type} URN should use colon between wagon and feature: {urn}"

        # Should NOT contain old format component:wagon.feature
        assert not urn.startswith(f"component:{parts[1]}."), \
            f"{artifact_type} URN should not use old dot format after wagon: {urn}"


def test_coder_complete_example_updated():
    """
    SPEC-CODER-CONV-0013: Complete example section updated with all four component URNs

    Verify the complete_example section has all URNs in new format.
    """
    with open(COMPONENT_NAMING_PATH) as f:
        convention = yaml.safe_load(f)

    complete_example = convention.get("complete_example", {})
    components = complete_example.get("components", [])

    assert len(components) >= 4, "Should have at least 4 component examples"

    for component in components:
        urn = component.get("urn", "")
        name = component.get("name", "")

        # All URNs should use colon format
        parts = urn.split(":")
        assert len(parts) >= 3, \
            f"{name} URN should have at least 3 colon-separated parts: {urn}"

        # Should be component:wagon:feature.component
        wagon = parts[1]
        feature_and_rest = parts[2]

        # Verify no dot immediately after component: (old format)
        assert not urn.startswith(f"component:{wagon}."), \
            f"{name} URN should not use old format component:wagon.feature: {urn}"


def test_green_convention_examples_updated():
    """
    SPEC-CODER-CONV-0014: Update coder green.convention.yaml component URN examples

    Verify green convention examples use new colon hierarchy.
    """
    with open(GREEN_CONV_PATH) as f:
        convention = yaml.safe_load(f)

    # urn_naming is nested under green_phase
    green_phase = convention.get("green_phase", {})
    examples = green_phase.get("urn_naming", {}).get("examples", [])

    assert len(examples) > 0, "Should have example URNs in green convention"

    for example in examples:
        urn = example.get("urn", "")
        wagon = example.get("wagon", "")
        feature = example.get("feature", "")

        # Should use new format: component:wagon:feature
        expected_prefix = f"component:{wagon}:{feature}"
        assert urn.startswith(expected_prefix), \
            f"URN should use colon hierarchy:\n  URN: {urn}\n  Expected prefix: {expected_prefix}"

        # Should NOT use old format: component:wagon.feature
        old_format = f"component:{wagon}.{feature}"
        assert not urn.startswith(old_format), \
            f"URN should not use old dot format: {urn}"


def test_green_convention_pattern_correct():
    """
    SPEC-CODER-CONV-0014: Green convention pattern field updated correctly

    Verify the pattern field in green.convention.yaml uses new format.
    """
    with open(GREEN_CONV_PATH) as f:
        convention = yaml.safe_load(f)

    # urn_naming is nested under green_phase
    green_phase = convention.get("green_phase", {})
    pattern = green_phase.get("urn_naming", {}).get("pattern", "")
    description = green_phase.get("urn_naming", {}).get("description", "")

    # Pattern should use colons for hierarchy
    assert "component:{wagon}:{feature}" in pattern, \
        f"Pattern should use colons: {pattern}"

    # Description should mention hierarchy via colons
    assert "hierarchy" in description.lower() or "colon" in description.lower(), \
        f"Description should mention hierarchy or colons: {description}"
