# URN: test:author-atdd-substrate:author-convention-node:E001-UNIT-001-flat-per-rule-file
# Acceptance: acc:author-atdd-substrate:E001-UNIT-001-flat-per-rule-file
# WMBT: wmbt:author-atdd-substrate:E001
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""E001-UNIT-001 — create_convention_node writes one flat schema-valid file."""
from __future__ import annotations

import pytest
import yaml

from atdd.planner.commands.author import (
    create_convention_node,
    validate_convention_node,
)


def test_creates_flat_schema_valid_node(tmp_path):
    path = create_convention_node(
        role="coder",
        rule_id="coder.green.component-urn-marker-is",
        statement="Implementation files must declare the component URN marker.",
        terms=[{"term_id": "urn_marker", "text": "Every file declares a URN marker."}],
        root=tmp_path,
    )
    # flat, under the role's nodes/ home, filename mirrors rule_id
    assert path == tmp_path / "coder" / "conventions" / "nodes" / "coder.green.component-urn-marker-is.convention.yaml"
    assert path.exists()
    node = yaml.safe_load(path.read_text())
    assert node["rule_id"] == "coder.green.component-urn-marker-is"
    assert node["kind"] in ("family", "rule", "principle", "constraint", "exception", "pattern", "anti_pattern", "policy")
    assert node["status"] in ("draft", "active", "deprecated")
    # the written node validates against the schema (no raise)
    validate_convention_node(node, path)


def test_optional_rationale_and_notes_emitted_in_spec_order(tmp_path):
    # spec §5.3: rationale + notes are optional-but-recommended; the command
    # emits them only when provided, in spec field order (statement→rationale→terms→notes).
    path = create_convention_node(
        role="coder",
        rule_id="coder.green.component-urn-marker-is",
        statement="Implementation files must declare the component URN marker.",
        rationale="The marker is how the graph locates a file's owning component.",
        notes="Legacy files without a marker are reported, not auto-fixed.",
        terms=[{"term_id": "urn_marker", "text": "Every file declares a URN marker."}],
        root=tmp_path,
    )
    node = yaml.safe_load(path.read_text())
    assert node["rationale"].startswith("The marker")
    assert node["notes"].startswith("Legacy files")
    validate_convention_node(node, path)
    keys = list(node.keys())
    assert keys.index("rationale") < keys.index("terms") < keys.index("notes")


def test_optional_fields_omitted_when_not_provided(tmp_path):
    path = create_convention_node(
        role="coder", rule_id="coder.green.no-extras",
        statement="A node with no rationale or notes omits those keys.",
        terms=[{"term_id": "x", "text": "y"}], root=tmp_path,
    )
    node = yaml.safe_load(path.read_text())
    assert "rationale" not in node and "notes" not in node
    assert "examples" not in node


def test_examples_and_term_values_emitted_in_spec_order(tmp_path):
    # §5.1: a node may carry positive/negative examples, and a term may carry
    # `values` (grammar / allowed-value maps) and its own positive/negative
    # examples. node-level examples sit between terms and notes (§5.1 order).
    path = create_convention_node(
        role="coder",
        rule_id="coder.green.component-urn-marker-is",
        statement="Implementation files must declare the component URN marker.",
        terms=[
            {
                "term_id": "urn_marker",
                "text": "Every implementation file declares a component URN marker.",
                "values": {"marker": "# URN:"},
                "examples": {"negative": ["import os\n# URN: component:checkout:pay:Card:backend:domain"]},
            },
        ],
        examples={
            "positive": ["# URN: component:checkout:payment:AuthorizeCard:backend:domain"],
            "negative": ["# Component: AuthorizeCard"],
        },
        notes="Legacy files without a marker are reported, not auto-fixed.",
        root=tmp_path,
    )
    node = yaml.safe_load(path.read_text())
    validate_convention_node(node, path)
    assert node["examples"]["positive"][0].startswith("# URN:")
    assert node["terms"][0]["values"]["marker"] == "# URN:"
    assert node["terms"][0]["examples"]["negative"]
    keys = list(node.keys())
    assert keys.index("terms") < keys.index("examples") < keys.index("notes")
