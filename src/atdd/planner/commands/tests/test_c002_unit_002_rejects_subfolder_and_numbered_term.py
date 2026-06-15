# URN: test:author-atdd-substrate:author-convention-node:C002-UNIT-002-rejects-subfolder-and-numbered-term
# Acceptance: acc:author-atdd-substrate:C002-UNIT-002-rejects-subfolder-and-numbered-term
# WMBT: wmbt:author-atdd-substrate:C002
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""C002-UNIT-002 — reject a semantic subfolder path and a numbered term id."""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.planner.commands.author import AuthorInputError, validate_convention_node


def _node(terms):
    return {
        "schema_version": "1.0.0",
        "rule_id": "coder.green.component-urn-marker-is",
        "kind": "rule",
        "status": "active",
        "statement": "x",
        "terms": terms,
    }


def test_rejects_numbered_term_id():
    with pytest.raises(AuthorInputError) as exc:
        validate_convention_node(
            _node([{"term_id": "T1", "text": "a"}]),
            Path("src/atdd/coder/conventions/nodes/coder.green.component-urn-marker-is.convention.yaml"),
        )
    assert exc.value.field == "terms"


def test_rejects_semantic_subfolder_path():
    with pytest.raises(AuthorInputError) as exc:
        validate_convention_node(
            _node([{"term_id": "urn_marker", "text": "a"}]),
            # semantic subfolder nodes/green/ is forbidden (spec §3.1 / D001)
            Path("src/atdd/coder/conventions/nodes/green/coder.green.component-urn-marker-is.convention.yaml"),
        )
    assert exc.value.field == "path"
