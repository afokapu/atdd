# URN: test:author-atdd-substrate:author-convention-node:C002-UNIT-001-rejects-bad-role-and-rule-id
# Acceptance: acc:author-atdd-substrate:C002-UNIT-001-rejects-bad-role-and-rule-id
# WMBT: wmbt:author-atdd-substrate:C002
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""C002-UNIT-001 — convention-node authoring rejects unknown role / malformed id."""
from __future__ import annotations

import pytest

from atdd.planner.commands.author import AuthorInputError, create_convention_node


def test_rejects_unknown_role(tmp_path):
    with pytest.raises(AuthorInputError) as exc:
        create_convention_node(
            role="nonsense", rule_id="nonsense.green.foo",
            statement="x", terms=[{"term_id": "a", "text": "a"}], root=tmp_path,
        )
    assert exc.value.field == "role"
    assert not (tmp_path / "nonsense").exists()


def test_rejects_malformed_rule_id(tmp_path):
    with pytest.raises(AuthorInputError) as exc:
        create_convention_node(
            role="coder", rule_id="coder.Green.BAD_ID",
            statement="x", terms=[{"term_id": "a", "text": "a"}], root=tmp_path,
        )
    assert exc.value.field == "rule_id"
