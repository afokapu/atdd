# URN: test:author-atdd-substrate:author-relationship:C003-UNIT-002-rejects-non-role-prefixed-id
# Acceptance: acc:author-atdd-substrate:C003-UNIT-002-rejects-non-role-prefixed-id
# WMBT: wmbt:author-atdd-substrate:C003
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""C003-UNIT-002 — validate_edge rejects a rule id that is not role-prefixed."""
from __future__ import annotations

import pytest

from atdd.planner.commands.author import AuthorInputError
from atdd.planner.commands.author_registry import validate_edge


def test_rejects_non_role_prefixed_target():
    edge = {
        "source_ref": "coder.green.a", "type": "enables",
        "target_ref": "notarole.green.b",  # first segment is not a known role
        "foundation": "finish_to_start", "constraint": "mandatory",
        "control": "internal", "strength": "critical",
    }
    with pytest.raises(AuthorInputError) as exc:
        validate_edge(edge)
    assert exc.value.field in ("target_ref", "ref")
