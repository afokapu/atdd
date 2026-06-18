# URN: test:author-plan-substrate:author-wmbt:C004-UNIT-001-rejects-bad-stepcode-and-statement
# Acceptance: acc:author-plan-substrate:C004-UNIT-001-rejects-bad-stepcode-and-statement
# WMBT: wmbt:author-plan-substrate:C004
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C004-UNIT-001 (plan wmbt) — create_wmbt rejects a statement missing its object_of_control token.

RED: create_wmbt / validate_wmbt do not exist yet.
"""
from __future__ import annotations

import pytest

from atdd.planner.commands.author import AuthorInputError, create_wmbt


def test_create_wmbt_rejects_statement_without_ooc_token(tmp_path):
    spec = {
        "wagon_slug": "demo-wagon",
        "code": "E001",
        "step": "execute",
        "direction": "maximize",
        "dimension": "likelihood",
        "object_of_control": "thing-creation",
        "context_clarifier": "when doing the thing",
        "lens": "functional.effectiveness",
        "statement": "maximize likelihood of something unrelated",  # omits 'thing-creation'
    }
    with pytest.raises(AuthorInputError):
        create_wmbt(spec, root=tmp_path)
    assert not (tmp_path / "plan" / "demo_wagon" / "E001.yaml").exists()
