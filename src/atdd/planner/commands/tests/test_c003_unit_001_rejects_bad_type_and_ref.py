# URN: test:author-atdd-substrate:author-relationship:C003-UNIT-001-rejects-bad-type-and-ref
# Acceptance: acc:author-atdd-substrate:C003-UNIT-001-rejects-bad-type-and-ref
# WMBT: wmbt:author-atdd-substrate:C003
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""C003-UNIT-001 — validate_edge rejects an invalid type and a malformed ref."""
from __future__ import annotations

import pytest

from atdd.planner.commands.author import AuthorInputError
from atdd.planner.commands.author_registry import validate_edge


def _edge(**over):
    e = {
        "source_ref": "coder.green.a", "type": "enables", "target_ref": "coder.green.b",
        "foundation": "finish_to_start", "constraint": "mandatory",
        "control": "internal", "strength": "critical",
    }
    e.update(over)
    return e


def test_rejects_invalid_type():
    with pytest.raises(AuthorInputError) as exc:
        validate_edge(_edge(type="depends_on_maybe"))
    assert exc.value.field == "type"


def test_rejects_malformed_ref():
    with pytest.raises(AuthorInputError) as exc:
        validate_edge(_edge(source_ref="coder.green.a#Bad Term"))
    assert exc.value.field in ("source_ref", "ref")
