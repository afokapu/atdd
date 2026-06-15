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
