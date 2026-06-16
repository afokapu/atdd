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


def test_110_blocks_emitted_in_canonical_order(tmp_path):
    # 1.1.0: identity → statement → implementation → source → content →
    # metadata → parity → terms. Each optional block is emitted only when given.
    path = create_convention_node(
        role="coder",
        rule_id="coder.green.component-urn-marker-is",
        name="Green: Component URN Marker",
        statement="Implementation files must declare the component URN marker.",
        implementation={"type": "validator", "ref": "test_component_urn::test_marker"},
        source={"legacy_path": "src/atdd/coder/conventions/green.convention.yaml",
                "extraction_mode": "high_fidelity"},
        content={
            "summary": "The marker is how the graph locates a file's owning component.",
            "operational_guidance": "Legacy files without a marker are reported, not auto-fixed.",
        },
        metadata={"severity": 3, "disposition": "suppress-and-clean"},
        parity={"source_fragments_preserved": True, "reviewed_at": "2026-06-16"},
        terms=[{"term_id": "urn_marker", "text": "Every file declares a URN marker."}],
        root=tmp_path,
    )
    node = yaml.safe_load(path.read_text())
    assert node["schema_version"] == "1.1.0"
    assert node["implementation"]["ref"].endswith("test_marker")
    assert node["content"]["summary"].startswith("The marker")
    assert node["metadata"]["severity"] == 3
    validate_convention_node(node, path)
    keys = list(node.keys())
    for a, b in (("statement", "implementation"), ("implementation", "source"),
                 ("source", "content"), ("content", "metadata"),
                 ("metadata", "parity"), ("parity", "terms")):
        assert keys.index(a) < keys.index(b), (a, b)


def test_optional_fields_omitted_when_not_provided(tmp_path):
    path = create_convention_node(
        role="coder", rule_id="coder.green.no-extras",
        statement="A node with no optional blocks omits those keys.",
        terms=[{"term_id": "x", "text": "y"}], root=tmp_path,
    )
    node = yaml.safe_load(path.read_text())
    for k in ("name", "implementation", "content", "metadata", "parity", "source"):
        assert k not in node


def test_term_values_and_examples_written_through(tmp_path):
    # a term may carry `values` (grammar / allowed-value maps) and its own
    # positive/negative examples; both are emitted verbatim.
    path = create_convention_node(
        role="coder",
        rule_id="coder.green.component-urn-marker-is",
        statement="Implementation files must declare the component URN marker.",
        content={
            "examples": ["# URN: component:checkout:payment:AuthorizeCard:backend:domain"],
            "counter_examples": ["# Component: AuthorizeCard"],
        },
        terms=[
            {
                "term_id": "urn_marker",
                "text": "Every implementation file declares a component URN marker.",
                "values": {"marker": "# URN:"},
                "examples": {"negative": ["import os\n# URN: component:checkout:pay:Card:backend:domain"]},
            },
        ],
        root=tmp_path,
    )
    node = yaml.safe_load(path.read_text())
    validate_convention_node(node, path)
    assert node["content"]["examples"][0].startswith("# URN:")
    assert node["terms"][0]["values"]["marker"] == "# URN:"
    assert node["terms"][0]["examples"]["negative"]
    keys = list(node.keys())
    assert keys.index("content") < keys.index("terms")
